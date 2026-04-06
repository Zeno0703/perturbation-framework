import json
import os
import re
from collections import defaultdict
from .config import get_out_dir, FILE_PROBES, FILE_HITS, FILE_OUTCOMES, FILE_PERTURBATIONS

_GENERIC_RE = re.compile(r'<.*?>')


def parse_probe(desc):
    parts = desc.rsplit(" in ", 1)
    if len(parts) != 2:
        return "unknown", "unknown", "unknown", "Unknown", "Unknown"

    mod = parts[0].replace("Modified ", "").strip()
    sig = parts[1].strip()

    mod_lower = mod.lower()
    if "return" in mod_lower:
        location, loc_abbr = "Return", "Ret"
    elif "argument" in mod_lower:
        location, loc_abbr = "Argument", "Arg"
    elif "variable" in mod_lower:
        location, loc_abbr = "Variable", "Var"
    else:
        location, loc_abbr = "Unknown", "Unk"

    if "boolean" in mod_lower:
        type_abbr = "Boolean"
    elif "integer" in mod_lower or "int " in mod_lower:
        type_abbr = "Integer"
    else:
        type_abbr = "Object"

    operator = f"{loc_abbr}-{type_abbr}"

    prefix = sig.split('(')[0].strip()
    tokens = prefix.split()
    if not tokens:
        return mod, "unknown", "unknown", location, operator

    fq_path = tokens[-1]
    segments = fq_path.split('.')
    if len(segments) < 2:
        return mod, fq_path, "unknown", location, operator

    is_constructor = (
        len(tokens) == 1
        or tokens[-2] in ('public', 'protected', 'private')
        or (segments[-1] and segments[-1][0].isupper())
    )

    if is_constructor:
        fqcn = fq_path
        method_name = segments[-1]
    else:
        fqcn = '.'.join(segments[:-1])
        method_name = segments[-1]

    fqcn = _GENERIC_RE.sub('', fqcn)
    method_name = _GENERIC_RE.sub('', method_name)

    return mod, fqcn, method_name, location, operator


def _read_jsonl(project_dir: str, filename: str) -> list[dict]:
    path = os.path.join(get_out_dir(project_dir), filename)
    results = []
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.strip()
                if not line: continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"[artifact_reader] {filename}:{lineno}: skipping malformed line: {exc}")
    except FileNotFoundError:
        pass
    return results


def read_probes(project_dir: str) -> dict[int, dict]:
    result = {}
    for obj in _read_jsonl(project_dir, FILE_PROBES):
        try:
            pid = int(obj["id"])
            result[pid] = {
                "desc": obj.get("description", f"probe {pid}"),
                "line": int(obj.get("line", -1)),
                "asmDescriptor": obj.get("asmDescriptor", "")
            }
        except (KeyError, TypeError, ValueError):
            pass
    return result


def read_hits(project_dir: str) -> defaultdict[int, set[str]]:
    hits: defaultdict[int, set[str]] = defaultdict(set)
    for obj in _read_jsonl(project_dir, FILE_HITS):
        try:
            test_name = obj.get("test", "")
            if test_name == "UNKNOWN_TEST":
                continue # IGNORING THE GHOST EXECUTION!
            hits[int(obj["probe_id"])].add(test_name)
        except (KeyError, TypeError, ValueError):
            pass
    return hits


def read_test_outcomes(project_dir: str) -> dict[str, str]:
    result = {}
    for obj in _read_jsonl(project_dir, FILE_OUTCOMES):
        try:
            test_name = obj.get("test", "")
            if test_name == "UNKNOWN_TEST":
                continue
            status = obj.get("outcome") or obj.get("status")
            if status:
                result[test_name] = status.strip()
        except (KeyError, AttributeError):
            pass
    return result


def read_perturbations(project_dir: str) -> defaultdict[str, list[str]]:
    actions_map: defaultdict[str, list[str]] = defaultdict(list)
    for obj in _read_jsonl(project_dir, FILE_PERTURBATIONS):
        try:
            test_name = obj.get("test", "")
            if test_name == "UNKNOWN_TEST":
                continue
            action = f"{obj['original']} -> {obj['perturbed']}"
            actions_map[test_name].append(action)
        except KeyError:
            pass
    return actions_map
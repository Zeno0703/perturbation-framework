import json
import os
import re
from collections import defaultdict

from .config import FILE_HITS, FILE_OUTCOMES, FILE_PERTURBATIONS, FILE_PROBES, get_out_dir

_GENERIC_RE = re.compile(r"<.*?>")


def parse_probe(description):
    parts = description.rsplit(" in ", 1)
    if len(parts) != 2:
        return "unknown", "unknown", "unknown", "Unknown", "Unknown"

    modifier = parts[0].replace("Modified ", "").strip()
    signature = parts[1].strip()

    modifier_lower = modifier.lower()
    if "return" in modifier_lower:
        location, location_abbreviation = "Return", "Ret"
    elif "argument" in modifier_lower:
        location, location_abbreviation = "Argument", "Arg"
    elif "variable" in modifier_lower:
        location, location_abbreviation = "Variable", "Var"
    else:
        location, location_abbreviation = "Unknown", "Unk"

    if "boolean" in modifier_lower:
        type_abbreviation = "Boolean"
    elif "integer" in modifier_lower or "int " in modifier_lower:
        type_abbreviation = "Integer"
    else:
        type_abbreviation = "Object"

    operator = f"{location_abbreviation}-{type_abbreviation}"

    signature_prefix = signature.split("(")[0].strip()
    signature_tokens = signature_prefix.split()
    if not signature_tokens:
        return modifier, "unknown", "unknown", location, operator

    fully_qualified_path = signature_tokens[-1]
    path_segments = fully_qualified_path.split(".")
    if len(path_segments) < 2:
        return modifier, fully_qualified_path, "unknown", location, operator

    is_constructor = (
        len(signature_tokens) == 1
        or signature_tokens[-2] in ("public", "protected", "private")
        or (path_segments[-1] and path_segments[-1][0].isupper())
    )

    if is_constructor:
        fully_qualified_class_name = fully_qualified_path
        method_name = path_segments[-1]
    else:
        fully_qualified_class_name = ".".join(path_segments[:-1])
        method_name = path_segments[-1]

    fully_qualified_class_name = _GENERIC_RE.sub("", fully_qualified_class_name)
    method_name = _GENERIC_RE.sub("", method_name)

    return modifier, fully_qualified_class_name, method_name, location, operator


def _read_jsonl(project_dir: str, filename: str) -> list[dict]:
    path = os.path.join(get_out_dir(project_dir), filename)
    results = []
    try:
        with open(path, encoding="utf-8") as jsonl_file:
            for line_number, raw_line in enumerate(jsonl_file, 1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"[artifact_reader] {filename}:{line_number}: skipping malformed line: {exc}")
    except FileNotFoundError:
        pass
    return results


def read_probes(project_dir: str) -> dict[int, dict]:
    result = {}
    for obj in _read_jsonl(project_dir, FILE_PROBES):
        try:
            probe_id = int(obj["id"])
            result[probe_id] = {
                "desc": obj.get("description", f"probe {probe_id}"),
                "line": int(obj.get("line", -1)),
                "asmDescriptor": obj.get("asmDescriptor", ""),
            }
        except (KeyError, TypeError, ValueError):
            pass
    return result


def read_hits(project_dir: str) -> defaultdict[int, set[str]]:
    hits: defaultdict[int, set[str]] = defaultdict(set)
    for obj in _read_jsonl(project_dir, FILE_HITS):
        try:
            hits[int(obj["probe_id"])].add(obj["test"])
        except (KeyError, TypeError, ValueError):
            pass
    return hits


def read_test_outcomes(project_dir: str) -> dict[str, str]:
    result = {}
    for obj in _read_jsonl(project_dir, FILE_OUTCOMES):
        try:
            result[obj["test"]] = obj["status"].strip()
        except (KeyError, AttributeError):
            pass
    return result


def read_perturbations(project_dir: str) -> defaultdict[str, list[str]]:
    actions_map: defaultdict[str, list[str]] = defaultdict(list)
    for obj in _read_jsonl(project_dir, FILE_PERTURBATIONS):
        try:
            action = f"{obj['original']} -> {obj['perturbed']}"
            actions_map[obj["test"]].append(action)
        except KeyError:
            pass
    return actions_map

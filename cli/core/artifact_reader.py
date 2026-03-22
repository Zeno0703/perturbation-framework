import json
import os
from collections import defaultdict

OUT_DIR = "target/perturb"


def _read_jsonl(project_dir: str, filename: str) -> list[dict]:
    """
    Parse a JSONL artifact file.

    Returns a list of parsed objects (one per non-empty line).
    Returns an empty list when the file does not exist.
    Skips and silently ignores any line that is not valid JSON — this makes
    the reader resilient to a truncated final line caused by an abrupt JVM
    shutdown.
    """
    path = os.path.join(project_dir, OUT_DIR, filename)
    results = []
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"[artifact_reader] {filename}:{lineno}: skipping malformed line: {exc}")
    except FileNotFoundError:
        pass
    return results


def read_probes(project_dir: str) -> dict[int, dict]:
    """
    Return a dict mapping probe_id (int) -> {"desc": str, "line": int, "asmDescriptor": str}.

    probes.txt schema: {"id": int, "description": str, "line": int, "asmDescriptor": str}
    """
    result = {}
    for obj in _read_jsonl(project_dir, "probes.txt"):
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
    """
    Return a defaultdict(set) mapping probe_id (int) -> set of test names
    that exercised that probe during the discovery run.

    hits.txt schema: {"probe_id": int, "test": str}
    """
    hits: defaultdict[int, set[str]] = defaultdict(set)
    for obj in _read_jsonl(project_dir, "hits.txt"):
        try:
            hits[int(obj["probe_id"])].add(obj["test"])
        except (KeyError, TypeError, ValueError):
            pass
    return hits


def read_test_outcomes(project_dir: str) -> dict[str, str]:
    """
    Return a dict mapping test_name -> status string (e.g. "PASS" or
    "FAIL (AssertionError)").

    test-outcomes.txt schema: {"test": str, "status": str}
    """
    result = {}
    for obj in _read_jsonl(project_dir, "test-outcomes.txt"):
        try:
            result[obj["test"]] = obj["status"].strip()
        except (KeyError, AttributeError):
            pass
    return result


def read_perturbations(project_dir: str) -> defaultdict[str, list[str]]:
    """
    Return a defaultdict(list) mapping test_name -> list of action strings.
    Each action string has the form "original -> perturbed", reconstructed
    from the structured fields so callers see the same shape as before.

    perturbations.txt schema: {"test": str, "original": str, "perturbed": str}
    """
    actions_map: defaultdict[str, list[str]] = defaultdict(list)
    for obj in _read_jsonl(project_dir, "perturbations.txt"):
        try:
            action = f"{obj['original']} -> {obj['perturbed']}"
            actions_map[obj["test"]].append(action)
        except KeyError:
            pass
    return actions_map
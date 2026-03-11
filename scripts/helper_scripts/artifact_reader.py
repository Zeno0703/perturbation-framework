import os
from collections import defaultdict

OUT_DIR = "target/perturb"


def unescape(text):
    """Reverse the Java-side tab-safe escaping applied to artifact values."""
    return (
        text
        .replace("\\\\", "\\")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
    )


def read_artifact(project_dir, filename):
    """
    Parse a two-column, tab-separated artifact file.

    Returns a list of [key, value] pairs, unescaping both columns.
    Returns an empty list when the file does not exist.
    """
    path = os.path.join(project_dir, OUT_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            result = []
            for line in f:
                if "\t" not in line:
                    continue
                parts = line.rstrip("\r\n").split("\t", 1)
                if len(parts) == 2:
                    result.append([unescape(parts[0]), unescape(parts[1])])
            return result
    except FileNotFoundError:
        return []


def read_probes(project_dir):
    """
    Return a dict mapping probe_id (int) -> description (str).
    """
    return {int(k): v for k, v in read_artifact(project_dir, "probes.txt")}


def read_hits(project_dir):
    """
    Return a defaultdict(set) mapping probe_id (int) -> set of test names
    that exercised that probe during the discovery run.
    """

    hits = defaultdict(set)
    for pid, test in read_artifact(project_dir, "hits.txt"):
        hits[int(pid)].add(test)
    return hits


def read_test_outcomes(project_dir):
    """
    Return a dict mapping test_name -> status string.
    """
    return {k: v.strip() for k, v in read_artifact(project_dir, "test-outcomes.txt")}


def read_perturbations(project_dir):
    """
    Return a defaultdict(list) mapping test_name -> list of action strings.
    """
    actions_map = defaultdict(list)
    for test_id, action in read_artifact(project_dir, "perturbations.txt"):
        actions_map[test_id].append(action)
    return actions_map
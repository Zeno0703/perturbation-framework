import json
import os

from .artifact_reader import parse_probe


def append_to_database(project_name, master_probes, hit_counts, db_path):
    probes_rows = []
    executions_rows = []

    for probe_id, probe_data in master_probes.items():
        probe_description = probe_data["desc"]
        modifier, fully_qualified_class_name, method_name, location, operator = parse_probe(probe_description)

        tests_hitting = sorted(probe_data["test_outcomes"].keys()) if probe_data["test_outcomes"] else []
        total_hits = sum(hit_counts[probe_id].get(test_name, 1) for test_name in tests_hitting)
        probe_outcome = probe_data["status"]

        probes_rows.append({
            "project": project_name,
            "probe_id": probe_id,
            "probe_desc": probe_description,
            "asmDescriptor": probe_data.get("asmDescriptor", ""),
            "line": probe_data.get("line", -1),
            "operator": operator,
            "location": location,
            "modifier": modifier,
            "fqcn": fully_qualified_class_name,
            "method": method_name,
            "total_hits":       total_hits,
            "unique_tests_hit": len(tests_hitting),
            "probe_outcome":    probe_outcome,
            "timed_out":        probe_outcome == "TIMEOUT",
        })

        for test_name, test_data in probe_data["test_outcomes"].items():
            outcome = test_data["outcome"]
            exception = test_data["exception"] or "none"

            if outcome == "clean":
                t_outcome, exc_family = "FAIL by Assert", "none"
                exception = "none"
            elif outcome == "dirty":
                t_outcome, exc_family = "FAIL by Exception", "JVM-Generic"
            elif outcome == "timeout":
                t_outcome, exc_family = "FAIL by Exception", "JVM-Timeout"
            else:
                t_outcome, exc_family = "PASS", "none"
                exception = "none"

            executions_rows.append({
                "project": project_name,
                "probe_id": probe_id,
                "test": test_name,
                "hits_in_test": hit_counts[probe_id].get(test_name, 1),
                "test_outcome": t_outcome,
                "exception": exception,
                "exception_family": exc_family,
                "perturbation_actions": [],
            })

    if os.path.isfile(db_path):
        try:
            with open(db_path, encoding="utf-8") as f:
                db = json.load(f)
        except json.JSONDecodeError:
            db = {"probes": [], "test_executions": []}
    else:
        db = {"probes": [], "test_executions": []}

    db["probes"].extend(probes_rows)
    db["test_executions"].extend(executions_rows)

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)

    print(
        f"JSON database updated : {db_path} "
        f"({len(db['probes'])} total probe rows)"
    )


def get_recorded_probes(db_path, project_name):
    if not os.path.isfile(db_path):
        return set()
    try:
        with open(db_path, encoding="utf-8") as f:
            db = json.load(f)
        return {p["probe_id"] for p in db.get("probes", []) if p.get("project") == project_name}
    except (json.JSONDecodeError, KeyError):
        return set()
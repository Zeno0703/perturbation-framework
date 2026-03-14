import os
import sys
import re
import time
import json
import argparse
from collections import defaultdict

from helper_scripts.maven_runner import run_maven
from helper_scripts.artifact_reader import (
    read_probes,
    read_test_outcomes,
    read_perturbations,
)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

PROJECTS = [
    {
        "dir": "/Users/zenovandenbulcke/Documents/jsemver",
        "package": "com.github.zafarkhaja.semver",
        "name": "JSemVer",
    },
    {
        "dir": "/Users/zenovandenbulcke/Documents/joda-money",
        "package": "org.joda.money",
        "name": "Joda-Money",
    },
    {
        "dir": "/Users/zenovandenbulcke/Documents/commons-cli",
        "package": "org.apache.commons.cli",
        "name": "Commons-CLI",
    },
    {
        "dir": "/Users/zenovandenbulcke/Documents/commons-csv",
        "package": "org.apache.commons.csv",
        "name": "Commons-CSV",
    },
    {
        "dir": "/Users/zenovandenbulcke/Documents/commons-validator",
        "package": "org.apache.commons.validator",
        "name": "Commons-Validator",
    },
    {
        "dir": "/Users/zenovandenbulcke/Documents/Textr",
        "package": "org.group02",
        "name": "Textr",
    },
]

DB_FILE = "database.json"

# ==============================================================================
# PROBE DESCRIPTION PARSING
# ==============================================================================

def parse_probe_desc(desc):
    """
    Extract structured fields from a probe description string.
    """
    parts = desc.rsplit(" in ", 1)
    if len(parts) != 2:
        return desc, "Unknown", "Unknown", "Unknown", "Unknown"

    modifier = parts[0].replace("Modified ", "").strip()
    sig = parts[1].strip()

    # Determine location
    mod_lower = modifier.lower()
    if "return" in mod_lower:
        location = "Return"
        loc_abbr = "Ret"
    elif "argument" in mod_lower:
        location = "Argument"
        loc_abbr = "Arg"
    elif "variable" in mod_lower:
        location = "Variable"
        loc_abbr = "Var"
    else:
        location = "Unknown"
        loc_abbr = "Unk"

    # Determine data type for operator
    if "boolean" in mod_lower:
        type_abbr = "Boolean"
    elif "integer" in mod_lower or "int " in mod_lower:
        type_abbr = "Integer"
    else:
        type_abbr = "Object"

    operator = f"{loc_abbr}-{type_abbr}"

    # Extract FQCN and method name from the signature
    cm_match = re.search(r'([\w\.\$]+)\.([\w\$<>\-]+)\(', sig)
    if cm_match:
        fqcn = cm_match.group(1)
        method = cm_match.group(2)
    else:
        constructor_match = re.search(r'([\w\.\$]+)\(', sig)
        if constructor_match:
            fqcn = constructor_match.group(1)
            method = fqcn.split('.')[-1]
        else:
            fqcn = "Unknown"
            method = "Unknown"

    return modifier, location, operator, fqcn, method


# ==============================================================================
# TEST OUTCOME PARSING
# ==============================================================================

def parse_test_outcome(status):
    """
    Normalise a raw Maven test-outcome status string into structured fields.
    """
    if not status or "PASS" in status.upper():
        return "PASS", "none", "none"

    status_up = status.upper()
    is_assertion = (
        "ASSERT" in status_up
        or "COMPARISON" in status_up
        or "MULTIPLEFAILURES" in status_up
    )

    if is_assertion:
        return "FAIL by Assert", "none", "none"

    exc_match = re.search(r'FAIL \((.*?)\)', status)
    exception_name = exc_match.group(1) if exc_match else "Unknown"
    return "FAIL by Exception", exception_name, "JVM-Generic"


def derive_probe_outcome(test_outcomes_list, is_timeout):
    """
    Determine overall probe outcome from the list of per-test outcome strings.

    Priority: Clean Kill > Dirty Kill > Survived
    """
    if is_timeout:
        return "Dirty Kill"
    has_exception_fail = False
    for outcome in test_outcomes_list:
        if outcome == "FAIL by Assert":
            return "Clean Kill"
        if outcome == "FAIL by Exception":
            has_exception_fail = True
    return "Dirty Kill" if has_exception_fail else "Survived"


# ==============================================================================
# PER-PROJECT PROCESSING
# ==============================================================================

def process_project(project, agent_jar):
    """
    Run the full discovery + evaluation pipeline for one project.
    """
    p_name = project["name"]
    p_dir = project["dir"]
    p_pkg = project["package"]

    # ── Phase 1: Discovery ─────────────────────────────────────────────────
    print(f"\n[{p_name}] Starting Discovery Phase...")
    disc_start = time.time()
    code, stderr, timed_out = run_maven(-1, p_dir, agent_jar, p_pkg)
    discovery_duration = time.time() - disc_start

    if code != 0 and not timed_out:
        print(f"[{p_name}] Discovery run returned non-zero exit code {code}. Proceeding anyway.")

    raw_probes = read_probes(p_dir)
    if not raw_probes:
        print(f"[{p_name}] No probes found after discovery. Skipping project.")
        return [], []

    # The LVT is a compiler-level setting applied globally via Maven's -g flag.
    # If ANY probe has a proper named description, the project has debug info
    # throughout. In that case we drop:
    #   1. JVM-slot probes ("(JVM slot N)") — compiler ghosts with no name.
    #   2. Probes with no description or an unparseable FQCN — these are probes
    #      registered via idForLocation but never described by ProbeCatalog
    #      (the "probe 190225529..." case: a ghost slot inside a method that
    #      otherwise has LVT entries for other slots).
    # If NO probe has a proper named description, debug info is globally absent
    # and we keep the JVM-slot probes as the only available information.
    def _is_named(d):
        # Named = has a real description, no JVM-slot tag, and a parseable FQCN
        if not d or re.search(r'\(JVM slot \d+\)', d):
            return False
        _, _, _, fq, _ = parse_probe_desc(d)
        return fq != "Unknown"

    project_has_named = any(_is_named(d) for d in raw_probes.values())

    if project_has_named:
        probes = {pid: desc for pid, desc in raw_probes.items() if _is_named(desc)}
        dropped = len(raw_probes) - len(probes)
        if dropped:
            print(f"[{p_name}] Filtered out {dropped} ghost/unnamed probe(s) "
                  f"(project has debug info; JVM-slot and undescribed probes excluded).")
    else:
        # No LVT anywhere, keep everything that at least has a parseable FQCN
        probes = {pid: desc for pid, desc in raw_probes.items()
                  if parse_probe_desc(desc)[3] != "Unknown"}
        print(f"[{p_name}] No debug info detected — keeping JVM-slot probes as fallback.")

    if not probes:
        print(f"[{p_name}] No actionable probes remain after filtering. Skipping project.")
        return [], []

    from helper_scripts.artifact_reader import read_artifact
    all_hit_pairs = read_artifact(p_dir, "hits.txt")

    hits = defaultdict(set)
    hit_counts = defaultdict(lambda: defaultdict(int))
    for pid_str, test in all_hit_pairs:
        pid_int = int(pid_str)
        if pid_int in probes:
            hits[pid_int].add(test)
            hit_counts[pid_int][test] += 1

    dynamic_timeout = max(discovery_duration * 2.0, 10.0)
    total_probes = len(probes)
    print(
        f"[{p_name}] Discovery done in {discovery_duration:.1f}s. "
        f"Found {total_probes} actionable probes. Timeout: {dynamic_timeout:.1f}s"
    )

    probes_db = []
    test_executions_db = []

    # ── Phase 2: Evaluation ────────────────────────────────────────────────
    for idx, (pid, desc) in enumerate(sorted(probes.items()), 1):
        tests_hitting_probe = sorted(hits.get(pid, set()))
        modifier, location, operator, fqcn, method = parse_probe_desc(desc)

        print(f"[{p_name}] ({idx}/{total_probes}) Probe {pid}: {desc[:80]}...")

        if not tests_hitting_probe:
            probes_db.append({
                "project": p_name,
                "probe_id": pid,
                "probe_desc": desc,
                "operator": operator,
                "location": location,
                "modifier": modifier,
                "fqcn": fqcn,
                "method": method,
                "total_hits": 0,
                "unique_tests_hit": 0,
                "probe_outcome": "Un-hit",
                "timed_out": False,
            })
            continue

        _, stderr, is_timeout = run_maven(
            pid, p_dir, agent_jar, p_pkg,
            timeout_limit=dynamic_timeout,
            targeted_tests=tests_hitting_probe,
        )

        outcomes = read_test_outcomes(p_dir)
        perturbations = read_perturbations(p_dir)

        test_outcomes_for_probe = []

        for test in tests_hitting_probe:
            hits_in_test = hit_counts[pid].get(test, 1)
            actions = perturbations.get(test, [])

            if is_timeout:
                t_outcome = "FAIL by Exception"
                exception = "TimeoutException"
                exc_family = "JVM-Timeout"
            else:
                raw_status = outcomes.get(test, "PASS")
                t_outcome, exception, exc_family = parse_test_outcome(raw_status)

            test_outcomes_for_probe.append(t_outcome)

            test_executions_db.append({
                "project": p_name,
                "probe_id": pid,
                "test": test,
                "hits_in_test": hits_in_test,
                "test_outcome": t_outcome,
                "exception": exception,
                "exception_family": exc_family,
                "perturbation_actions": actions,
            })

        probe_outcome = derive_probe_outcome(test_outcomes_for_probe, is_timeout)
        total_hits = sum(hit_counts[pid].get(t, 1) for t in tests_hitting_probe)

        probes_db.append({
            "project": p_name,
            "probe_id": pid,
            "probe_desc": desc,
            "operator": operator,
            "location": location,
            "modifier": modifier,
            "fqcn": fqcn,
            "method": method,
            "total_hits": total_hits,
            "unique_tests_hit": len(tests_hitting_probe),
            "probe_outcome": probe_outcome,
            "timed_out": is_timeout,
        })

    return probes_db, test_executions_db


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run perturbation tests across projects and dump results to database.json"
    )
    parser.add_argument("agent_jar", help="Path to the perturb-agent JAR file")
    parser.add_argument(
        "--output", default=DB_FILE,
        help=f"Output JSON file path (default: {DB_FILE})"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.agent_jar):
        sys.exit(f"Agent JAR not found: {args.agent_jar}")

    if not PROJECTS:
        sys.exit("No projects configured in PROJECTS list. Exiting.")

    # ── Load existing database ──────────────────────────────
    # If the output file already exists, load it and skip any projects that
    # are already present. Delete the file to force a full re-run.
    if os.path.isfile(args.output):
        with open(args.output, encoding="utf-8") as f:
            final_db = json.load(f)
        already_done = {p["project"] for p in final_db.get("probes", [])}
        if already_done:
            print(f"Found existing database at '{args.output}' "
                  f"with {len(already_done)} project(s) already recorded: "
                  f"{', '.join(sorted(already_done))}.")
            print("These will be skipped. Delete the file to force a full re-run.")
    else:
        final_db = {"probes": [], "test_executions": []}
        already_done = set()

    script_start = time.time()

    for project in PROJECTS:
        p_name = project["name"]
        p_dir = project["dir"]

        if p_name in already_done:
            print(f"[{p_name}] Already in database. Skipping.")
            continue

        if not os.path.isdir(p_dir):
            print(f"[{p_name}] Project directory not found: {p_dir}. Skipping.")
            continue

        try:
            probes, executions = process_project(project, args.agent_jar)
            final_db["probes"].extend(probes)
            final_db["test_executions"].extend(executions)
            print(
                f"[{p_name}] Done — {len(probes)} probes, "
                f"{len(executions)} test executions recorded."
            )
        except Exception as e:
            print(f"[{p_name}] FAILED: {e}. Skipping project and continuing.")
            continue

        # Write after each project so a crash doesn't lose earlier results
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(final_db, f, indent=2)

    total_time = time.time() - script_start
    print(
        f"\nAll done in {total_time:.1f}s. "
        f"Database now contains {len(final_db['probes'])} probes and "
        f"{len(final_db['test_executions'])} test executions in '{args.output}'."
    )


if __name__ == "__main__":
    main()
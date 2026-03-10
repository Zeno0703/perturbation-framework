import os
import sys
import subprocess
import time
import signal
import json
import re
from collections import defaultdict

# ==============================================================================
# CONFIGURATION
# ==============================================================================
AGENT_JAR = "/Users/zenovandenbulcke/Library/CloudStorage/OneDrive-Personal/Documents/KU LEUVEN-Zeno/2e Master/Master Thesis/Perturbation Testing/Tool/perturb-agent/target/perturb-agent-1.0-SNAPSHOT.jar"

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
    }
]

OUT_DIR = "target/perturb"
DB_FILE = "database.json"


# ==============================================================================
# UTILITIES & PARSING
# ==============================================================================
def clear_artifacts(project_dir):
    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    for name in ("probes.txt", "hits.txt", "test-outcomes.txt", "perturbations.txt"):
        path = os.path.join(target, name)
        if os.path.exists(path):
            os.remove(path)


def unescape(text):
    return text.replace("\\\\", "\\").replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")


def read_artifact(project_dir, filename):
    path = os.path.join(project_dir, OUT_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            result = []
            for line in f:
                if "\t" not in line:
                    continue
                parts = line.rstrip("\r\n").split("\t", 1)
                if len(parts) == 2:
                    result.append((unescape(parts[0]), unescape(parts[1])))
            return result
    except FileNotFoundError:
        return []


def parse_probe_desc(desc):
    # Extracts modifier, FQCN, and method name
    match = re.search(
        r'^(.*?) in (?:(?:public|private|protected|static|final|abstract|synchronized)\s+)*[\w\.\$\[\]<>]+\s+([\w\.\$]+)\.([\w\$]+)\(',
        desc)
    if not match:
        return desc, "Unknown", "Unknown", "Unknown", "Unknown"

    modifier_text = match.group(1).strip()
    fqcn = match.group(2)
    method = match.group(3)

    location = "Unknown"
    mod_lower = modifier_text.lower()
    if "return" in mod_lower:
        location = "Return"
    elif "argument" in mod_lower:
        location = "Argument"
    elif "variable" in mod_lower:
        location = "Variable"

    type_match = re.search(r'(?:Modified|Added|Flipped|Removed)\s+([\w\.\$\[\]]+)\s+', modifier_text, re.IGNORECASE)
    data_type = type_match.group(1).capitalize() if type_match else "Unknown"

    operator = f"{location[:3]}-{data_type}" if location != "Unknown" else "Unknown"
    return modifier_text, location, operator, fqcn, method


def parse_test_outcome(status):
    status_up = status.upper()
    if not status or "PASS" in status_up:
        return "PASS", "none", "none"

    exception_name = "none"
    exc_match = re.search(r'FAIL \((.*?)\)', status)
    if exc_match:
        exception_name = exc_match.group(1)

    is_assertion = "ASSERT" in status_up or "COMPARISON" in status_up or "MULTIPLEFAILURES" in status_up

    if is_assertion:
        return "FAIL by Assert", "none", "none"
    else:
        exc_fam = "JVM-Generic" if exception_name != "none" else "Unknown"
        return "FAIL by Exception", exception_name, exc_fam


def derive_probe_outcome(test_outcomes, is_timeout):
    if is_timeout:
        return "Dirty Kill"

    has_exception = False
    for t_out in test_outcomes:
        if t_out == "FAIL by Assert":
            return "Clean Kill"  # Clean Kill takes precedence
        if t_out == "FAIL by Exception":
            has_exception = True

    return "Dirty Kill" if has_exception else "Survived"


# ==============================================================================
# EXECUTION
# ==============================================================================
def run_maven(probe_id, project_dir, target_package, timeout_limit=None, targeted_tests=None):
    clear_artifacts(project_dir)
    arg_line = (
        f'-javaagent:"{AGENT_JAR}" '
        f'-Dperturb.package={target_package} '
        f'-Dperturb.outDir={OUT_DIR} '
        f'-Dperturb.activeProbe={probe_id} '
        '-Dorg.agent.hidden.bytebuddy.experimental=true'
    )
    command = [
        "mvn", "test",
        f'-DargLine={arg_line}',
        "-Djunit.jupiter.extensions.autodetection.enabled=true",
        "-Djacoco.skip=true"
    ]
    if targeted_tests:
        command.append(f'-Dtest={",".join(targeted_tests)}')

    try:
        process = subprocess.Popen(
            command, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True
        )
        _, stderr = process.communicate(timeout=timeout_limit)
        return process.returncode, False
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.communicate()
        return -1, True


def process_project(project):
    p_name = project["name"]
    p_dir = project["dir"]
    p_pkg = project["package"]

    print(f"[{p_name}] Starting Discovery Phase...")
    start_time = time.time()
    code, _ = run_maven(-1, p_dir, p_pkg)
    discovery_duration = time.time() - start_time

    probes_raw = read_artifact(p_dir, "probes.txt")
    if not probes_raw:
        print(f"[{p_name}] No probes found. Skipping.")
        return [], []

    hits_raw = read_artifact(p_dir, "hits.txt")
    hits = defaultdict(list)
    hit_counts = defaultdict(lambda: defaultdict(int))

    for pid_str, test in hits_raw:
        pid = int(pid_str)
        hits[pid].append(test)
        hit_counts[pid][test] += 1

    dynamic_timeout = max(discovery_duration * 2.0, 10.0)
    total_probes = len(probes_raw)
    print(f"[{p_name}] Discovery done. Evaluating {total_probes} probes (Timeout: {dynamic_timeout:.1f}s)")

    probes_db = []
    test_executions_db = []

    for idx, (pid_str, desc) in enumerate(probes_raw, 1):
        pid = int(pid_str)
        tests_hitting_probe = list(set(hits.get(pid, [])))

        print(f"[{p_name}] Evaluating probe {idx}/{total_probes} (ID: {pid})...")

        if not tests_hitting_probe:
            continue

        modifier, location, operator, fqcn, method = parse_probe_desc(desc)

        _, is_timeout = run_maven(pid, p_dir, p_pkg, timeout_limit=dynamic_timeout, targeted_tests=tests_hitting_probe)
        outcomes = {k: v.strip() for k, v in read_artifact(p_dir, "test-outcomes.txt")}

        test_outcomes_for_probe = []

        # 1. Process Test Executions
        for test in tests_hitting_probe:
            status = outcomes.get(test, "PASS")

            if is_timeout:
                t_outcome, exc, exc_fam = "FAIL by Exception", "TimeoutException", "JVM-Timeout"
            else:
                t_outcome, exc, exc_fam = parse_test_outcome(status)

            test_outcomes_for_probe.append(t_outcome)

            test_executions_db.append({
                "project": p_name,
                "probe_id": pid,
                "test": test,
                "hits_in_test": hit_counts[pid][test],
                "test_outcome": t_outcome,
                "exception": exc,
                "exception_family": exc_fam
            })

        # 2. Process Probe Aggregation
        p_outcome = derive_probe_outcome(test_outcomes_for_probe, is_timeout)
        total_hits = sum(hit_counts[pid].values())

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
            "probe_outcome": p_outcome,
            "timed_out": is_timeout
        })

    return probes_db, test_executions_db


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    if not PROJECTS:
        print("No projects configured. Exiting.")
        sys.exit(0)

    final_db = {
        "probes": [],
        "test_executions": []
    }

    for project in PROJECTS:
        try:
            probes, executions = process_project(project)
            final_db["probes"].extend(probes)
            final_db["test_executions"].extend(executions)
            print(
                f"[{project['name']}] Successfully processed {len(probes)} probes and {len(executions)} test executions.")
        except Exception as e:
            print(f"[{project['name']}] FAILED during execution: {e}")
            continue

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(final_db, f, indent=2)

    print(
        f"\nExecution complete. Dumped {len(final_db['probes'])} probes and {len(final_db['test_executions'])} execution records to {DB_FILE}.")


if __name__ == "__main__":
    main()
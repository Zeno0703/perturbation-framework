import os
import sys
import subprocess
import time
import signal
from collections import defaultdict

OUT_DIR = "target/perturb"
ARTIFACTS = ("probes.txt", "hits.txt", "test-outcomes.txt", "perturbations.txt")


def clear_artifacts(project_dir):
    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    for name in ARTIFACTS:
        path = os.path.join(target, name)
        if os.path.exists(path):
            os.remove(path)


def run_maven(probe_id, project_dir, agent_jar, target_package, timeout_limit=None, targeted_tests=None):
    clear_artifacts(project_dir)

    arg_line = (
        f'-javaagent:"{agent_jar}" '
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
            preexec_fn=os.setsid
        )
        _, stderr = process.communicate(timeout=timeout_limit)
        return process.returncode, stderr, False

    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        return -1, "PROCESS TIMED OUT", True


def unescape(text):
    return text.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t").replace("\\\\", "\\")

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
                    key = unescape(parts[0])
                    val = unescape(parts[1])
                    result.append([key, val])

            return result
    except FileNotFoundError:
        return []

def discovery(project_dir, agent_jar, target_package):
    print("Running Discovery Phase...")
    start_time = time.time()

    code, stderr, _ = run_maven(-1, project_dir, agent_jar, target_package)
    discovery_duration = time.time() - start_time
    print(f"Discovery finished in {discovery_duration:.2f} seconds.")

    if code != 0:
        sys.exit(f"Discovery failed:\n{stderr[-1000:]}")

    probes = {int(k): v for k, v in read_artifact(project_dir, "probes.txt")}
    if not probes:
        sys.exit("No probes found.")

    hits = defaultdict(set)
    for pid, test in read_artifact(project_dir, "hits.txt"):
        hits[int(pid)].add(test)

    return probes, hits, discovery_duration


def evaluate(probe_id, tests, project_dir, agent_jar, target_package, timeout_limit):
    code, stderr, timed_out = run_maven(probe_id, project_dir, agent_jar, target_package, timeout_limit,
                                        targeted_tests=tests)

    if timed_out:
        print(f"  - TIMEOUT! Run exceeded {timeout_limit:.2f} seconds.\n  Result: Discarded (Infinite Loop Detected)")
        return None, True

    outcomes = {k: v.strip().upper() for k, v in read_artifact(project_dir, "test-outcomes.txt")}
    if not outcomes:
        print(f"  No outcomes produced:\n{stderr[-1000:]}")
        return None, False

    actions_map = {}
    for test_id, action in read_artifact(project_dir, "perturbations.txt"):
        if test_id not in actions_map:
            actions_map[test_id] = []
        if action not in actions_map[test_id]:
            actions_map[test_id].append(action)

    failed = sum(1 for test in tests if outcomes.get(test, "MISSING") not in ("PASS", "MISSING"))
    passed = sum(1 for test in tests if outcomes.get(test, "MISSING") == "PASS")

    for test in sorted(tests):
        status = outcomes.get(test, 'MISSING')
        test_actions = actions_map.get(test, [])
        action_str = f"  ({', '.join(test_actions)})" if test_actions else ""

        print(f"  - {test}: {status}{action_str}")

    total = failed + passed
    if total == 0:
        print("  Score: N/A")
        return None, False

    score = failed / total
    print(f"  Caught Perturbations: {score * 100:.2f}% ({failed}/{total})")
    return score, False


def main():
    if len(sys.argv) != 4:
        sys.exit("Usage: python3 run-agent.py <project_dir> <agent_jar> <target_package>")

    script_start = time.time()
    project_dir, agent_jar, target_package = sys.argv[1:4]

    probes, hits, discovery_duration = discovery(project_dir, agent_jar, target_package)
    dynamic_timeout = max(discovery_duration * 2.0, 10.0)
    print(f"Set strict timeout limit for evaluations: {dynamic_timeout:.2f} seconds")

    scores = []
    timeouts_count = skipped_count = errors_count = 0

    for pid, probe_desc in sorted(probes.items()):
        print(f"\nProbe {pid}: {probe_desc}")
        tests = hits.get(pid)

        if not tests:
            print("  SKIP: No tests hit this probe")
            skipped_count += 1
            continue

        score, is_timeout = evaluate(pid, tests, project_dir, agent_jar, target_package, dynamic_timeout)

        if is_timeout:
            timeouts_count += 1
        elif score is not None:
            scores.append(score)
        else:
            errors_count += 1

    total_duration = time.time() - script_start
    mean_score_str = f"{sum(scores) / len(scores) * 100:.2f}%" if scores else "N/A"

    print(f"""
        {'=' * 50}
                         FINAL ANALYTICS
        {'=' * 50}
        Total Probes Discovered : {len(probes)}
        Probes Scored           : {len(scores)}
        Probes Skipped (No Hit) : {skipped_count}
        Timeouts (Discarded)    : {timeouts_count}
        Errors (No Outcomes)    : {errors_count}
        {'-' * 50}
        Discovery Runtime       : {discovery_duration:.2f}s
        Evaluation Runtime      : {total_duration - discovery_duration:.2f}s
        Total Script Runtime    : {total_duration:.2f}s
        {'-' * 50}
        Mean Perturbation Score : {mean_score_str}
        {'=' * 50}
        """)


if __name__ == "__main__":
    main()
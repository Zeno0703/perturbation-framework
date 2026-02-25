import os
import sys
import subprocess

OUT_DIR = "target/perturb"
ARTIFACTS = ("probes.txt", "hits.txt", "test-outcomes.txt")

def clear_artifacts(project_dir):
    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    for name in ARTIFACTS:
        path = os.path.join(target, name)
        if os.path.exists(path):
            os.remove(path)

def run_maven(probe_id, project_dir, agent_jar, target_package):
    clear_artifacts(project_dir)
    command = (
        f'mvn test -DargLine="-javaagent:\'{agent_jar}\' '
        f'-Dperturb.package={target_package} '
        f'-Djunit.jupiter.extensions.autodetection.enabled=true '
        f'-Dperturb.outDir={OUT_DIR} '
        f'-Dperturb.activeProbe={probe_id} '
        f'-Dorg.agent.hidden.bytebuddy.experimental=true" '
        f'-Djacoco.skip=true'
    )
    result = subprocess.run(command, shell=True, cwd=project_dir, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def main():
    if len(sys.argv) != 4:
        sys.exit("Usage: python3 run-discovery.py <project_dir> <agent_jar> <target_package>")

    project_dir, agent_jar, target_package = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f"Running Maven tests on {target_package} with probe '-1'...")

    code, stdout, stderr = run_maven(-1, project_dir, agent_jar, target_package)

    if code != 0:
        sys.exit(f"Run failed!\n\n--- STDOUT ---\n{stdout[-1000:]}\n\n--- STDERR ---\n{stderr[-1000:]}")

    print(f"Run complete. Artifacts saved to {os.path.join(project_dir, OUT_DIR)}")

    #if stderr and stderr.strip():
    #    print("\n--- BYTEBUDDY STDERR LOGS ---")
    #    print(stderr)

if __name__ == "__main__":
    main()
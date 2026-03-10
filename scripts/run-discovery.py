import os
import sys
import subprocess


def main():
    if len(sys.argv) != 4:
        sys.exit("Usage: python3 run-discovery.py <project_dir> <agent_jar> <target_package>")

    project_dir, agent_jar, target_package = sys.argv[1:4]

    target_out_dir = os.path.join(project_dir, "target/perturb")
    os.makedirs(target_out_dir, exist_ok=True)

    for name in ("probes.txt", "hits.txt", "test-outcomes.txt", "perturbations.txt"):
        artifact_path = os.path.join(target_out_dir, name)
        if os.path.exists(artifact_path):
            os.remove(artifact_path)

    arg_line = (
        f'-javaagent:"{agent_jar}" '
        f'-Dperturb.package={target_package} '
        f'-Dperturb.outDir=target/perturb '
        f'-Dperturb.activeProbe=-1 '
        '-Dorg.agent.hidden.bytebuddy.experimental=true'
        '-Xshare:off'
        '-XX:+EnableDynamicAgentLoading'
    )

    command = [
        "mvn", "test",
        f'-DargLine={arg_line}',
        "-Djunit.jupiter.extensions.autodetection.enabled=true",
        "-Djacoco.skip=true"
    ]

    try:
        subprocess.run(command, cwd=project_dir, check=True, capture_output=True, text=True)
        print("Discovery run completed successfully.")

    except subprocess.CalledProcessError as e:
        sys.exit(f"Discovery run failed:\n{e.stderr[-1000:] if e.stderr else e.stdout[-1000:]}")


if __name__ == "__main__":
    main()
import os
import subprocess
import signal

OUT_DIR = "target/perturb"
ARTIFACTS = ("probes.txt", "hits.txt", "test-outcomes.txt", "perturbations.txt")

def clear_artifacts(project_dir):
    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    for name in ARTIFACTS:
        path = os.path.join(target, name)
        if os.path.exists(path):
            os.remove(path)

def run_maven(probe_id, project_dir, agent_jar, target_package,
              timeout_limit=None, targeted_tests=None, maven_goal="test"):
    """
    Execute Maven with the perturbation agent attached.
    Added 'maven_goal' to allow bypassing the compile lifecycle.
    """
    clear_artifacts(project_dir)

    arg_line = (
        f'-javaagent:"{agent_jar}" '
        f'-Dperturb.package={target_package} '
        f'-Dperturb.outDir={OUT_DIR} '
        f'-Dperturb.activeProbe={probe_id} '
        '-Dorg.agent.hidden.bytebuddy.experimental=true '
        '-Xshare:off '
        '-XX:+EnableDynamicAgentLoading'
    )

    command = [
        "mvn", maven_goal,
        f'-DargLine={arg_line}',
        "-Djunit.jupiter.extensions.autodetection.enabled=true",
        "-Djacoco.skip=true",
        "-Drat.skip=true",
        "-Dcheckstyle.skip=true",
    ]

    if targeted_tests:
        command.append(f'-Dtest={",".join(targeted_tests)}')

    try:
        process = subprocess.Popen(
            command, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )
        output, _ = process.communicate(timeout=timeout_limit)
        return process.returncode, output, False

    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.communicate()
        return -1, "PROCESS TIMED OUT", True
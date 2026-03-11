import os
import subprocess
import signal

OUT_DIR = "target/perturb"
ARTIFACTS = ("probes.txt", "hits.txt", "test-outcomes.txt", "perturbations.txt")


def clear_artifacts(project_dir):
    """Remove all known artifact files so stale data cannot bleed into a new run."""
    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    for name in ARTIFACTS:
        path = os.path.join(target, name)
        if os.path.exists(path):
            os.remove(path)


def run_maven(probe_id, project_dir, agent_jar, target_package,
              timeout_limit=None, targeted_tests=None):
    """
    Execute 'mvn test' with the perturbation agent attached.

    Parameters
    ----------
    probe_id        : int   — the probe to activate (-1 for discovery).
    project_dir     : str   — root directory of the Maven project.
    agent_jar       : str   — path to the Java agent JAR.
    target_package  : str   — package the agent should instrument.
    timeout_limit   : float — seconds before the process is killed (None = unlimited).
    targeted_tests  : list  — optional list of test class/method names to run.

    Returns
    -------
    (returncode: int, stderr: str, timed_out: bool)
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
        "mvn", "test",
        f'-DargLine={arg_line}',
        "-Djunit.jupiter.extensions.autodetection.enabled=true",
        "-Djacoco.skip=true",
    ]

    if targeted_tests:
        command.append(f'-Dtest={",".join(targeted_tests)}')

    try:
        process = subprocess.Popen(
            command, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        _, stderr = process.communicate(timeout=timeout_limit)
        return process.returncode, stderr, False

    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.communicate()
        return -1, "PROCESS TIMED OUT", True
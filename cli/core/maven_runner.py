import os
import subprocess
import platform
import signal
from .config import get_out_dir, OUT_DIR_NAME, FILE_PROBES, FILE_HITS, FILE_OUTCOMES, FILE_PERTURBATIONS

ARTIFACTS = (FILE_PROBES, FILE_HITS, FILE_OUTCOMES, FILE_PERTURBATIONS)

def clear_artifacts(project_dir):
    target = get_out_dir(project_dir)
    os.makedirs(target, exist_ok=True)
    for name in ARTIFACTS:
        path = os.path.join(target, name)
        if os.path.exists(path):
            os.remove(path)


def run_maven(probe_id, project_dir, agent_jar, target_package,
              timeout_limit=None, targeted_tests=None, maven_goal="test"):
    # Each run starts from clean artifact files so parsers only see fresh data.
    clear_artifacts(project_dir)

    arg_line = (
        f'-javaagent:"{agent_jar}" '
        f'-Dperturb.package={target_package} '
        f'-Dperturb.outDir={OUT_DIR_NAME} '
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
        # Pre-exec function needed on POSIX to assign a process group ID
        is_windows = platform.system() == "Windows"

        process = subprocess.Popen(
            command, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=not is_windows  # Creates a new process group on POSIX
        )
        output, _ = process.communicate(timeout=timeout_limit)
        return process.returncode, output, False

    except subprocess.TimeoutExpired:
        # Cross-platform Process Tree Kill
        if platform.system() == "Windows":
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception:
                process.kill()  # Absolute fallback

        process.communicate()
        return -1, "PROCESS TIMED OUT", True
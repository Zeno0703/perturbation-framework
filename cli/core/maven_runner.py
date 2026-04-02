import os
import subprocess

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
        process = subprocess.Popen(
            command, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        combined_output, _ = process.communicate(timeout=timeout_limit)
        return process.returncode, combined_output, False

    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        return -1, "PROCESS TIMED OUT", True
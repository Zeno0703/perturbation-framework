import os
import sys
import time
import webbrowser

from helper_scripts.probe_analyser import discovery, run_analysis, format_analytics
from helper_scripts.dashboard_builder import generate_dashboard

OUT_DIR = "target/perturb"


def main():
    if len(sys.argv) != 4:
        sys.exit("Usage: python3 run_agent_web.py <project_dir> <agent_jar> <target_package>")

    script_start = time.time()
    project_dir, agent_jar, target_package = sys.argv[1:4]

    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    log_path = os.path.join(target, "execution.log")
    log_file = open(log_path, "w", encoding="utf-8")

    try:
        # ── Phase 1: Discovery ─────────────────────────────────────────────
        probes, hits, discovery_duration = discovery(
            project_dir, agent_jar, target_package, log_file,
        )
        dynamic_timeout = max(discovery_duration * 2.0, 10.0)
        log_file.write(
            f"Set strict timeout limit for evaluations: {dynamic_timeout:.2f} seconds\n"
        )

        # ── Phase 2: Evaluation ────────────────────────────────────────────
        (
            master_probes,
            dashboard_ledger,
            dashboard_methods,
            dashboard_tests,
            test_summary,
            metrics,
            global_tier3_probes,
        ) = run_analysis(
            probes, hits, project_dir, agent_jar, target_package,
            dynamic_timeout, log_file,
        )

        # ── Phase 3: Analytics summary ────────────────────────────────────
        analytics_text = format_analytics(metrics)
        print(analytics_text)
        log_file.write(analytics_text + "\n")

        total_duration = time.time() - script_start
        log_file.write(f"Total wall-clock time: {total_duration:.2f} seconds\n")

        # ── Phase 4: Dashboard generation ─────────────────────────────────
        html_file = generate_dashboard(
            project_dir,
            dashboard_ledger,
            dashboard_methods,
            dashboard_tests,
            test_summary,
            metrics,
            global_tier3_probes,
            master_probes,
        )

        log_file.write(f"\nDashboard generated at: {html_file}\n")
        print(f"\nDashboard generated at: {html_file}")

    finally:
        log_file.close()

    webbrowser.open('file://' + os.path.realpath(html_file))


if __name__ == "__main__":
    main()
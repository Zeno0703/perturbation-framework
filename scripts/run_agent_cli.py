import os
import sys
import time

from helper_scripts.probe_analyser import discovery, run_analysis, format_analytics

OUT_DIR = "target/perturb"


def main():
    args = sys.argv[1:]

    discovery_only = "--discovery-only" in args
    if discovery_only:
        args.remove("--discovery-only")

    if len(args) != 3:
        sys.exit(
            "Usage: python3 run_agent.py <project_dir> <agent_jar> <target_package> [--discovery-only]\n"
            "Example: python3 run_agent.py ./my-project ./agent.jar org.example --discovery-only"
        )

    script_start = time.time()
    project_dir, agent_jar, target_package = args

    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    log_path = os.path.join(target, "execution.log")
    log_file = open(log_path, "w", encoding="utf-8")

    try:
        # ── Phase 1: Discovery ─────────────────────────────────────────────
        probes, hits, discovery_duration = discovery(
            project_dir, agent_jar, target_package, log_file,
        )

        if discovery_only:
            msg = f"\n[INFO] Discovery run completed. Found {len(probes)} probes.\nArtifacts saved in {target}\n"
            print(msg)
            log_file.write(msg)
            return

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

        print(f"Total wall-clock time: {total_duration:.2f} seconds")
        print(f"Execution log and artifacts saved at: {target}")

    finally:
        log_file.close()


if __name__ == "__main__":
    main()
import sys
import os
# This lets `python main_isolated.py ...` work even when the package is not installed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import argparse
import sys
import time
import webbrowser
from collections import defaultdict

# IMPORT FROM THE ISOLATED ANALYSER INSTEAD
from core.probe_analyser_isolated import discovery, run_analysis, format_analytics
from core.dashboard_builder import generate_dashboard
from core.db_exporter import append_to_database, get_recorded_probes
from core.config import get_out_dir, DEFAULT_DB_PATH


def export_stdout(metrics, analytics_text, project_dir, total_duration):
    print(analytics_text)
    print(f"Total wall-clock time : {total_duration:.2f}s")
    print(f"Artifacts saved in    : {get_out_dir(project_dir)}")


def export_html(project_dir, dashboard_ledger, dashboard_methods, dashboard_tests, test_summary,
                metrics, global_tier3_probes, master_probes, no_browser=False):
    html_file = generate_dashboard(project_dir, dashboard_ledger, dashboard_methods, dashboard_tests,
                                   test_summary, metrics, global_tier3_probes, master_probes)
    print(f"Dashboard generated at: {html_file}")
    if not no_browser:
        webbrowser.open("file://" + os.path.realpath(html_file))


def export_json(project_name, master_probes, hits, db_path):
    hit_counts = defaultdict(lambda: defaultdict(int))
    for probe_id, tests_set in hits.items():
        for test_name in tests_set:
            hit_counts[probe_id][test_name] += 1
    append_to_database(project_name, master_probes, hit_counts, db_path)


def run_single_project(project_dir, agent_jar, target_package, formats, db_path, discovery_only,
                       no_browser, project_name=None, batch_size=100, redo=False):
    target = get_out_dir(project_dir)
    os.makedirs(target, exist_ok=True)
    log_path = os.path.join(target, "execution.log")

    resolved_project_name = project_name or os.path.basename(os.path.abspath(project_dir))
    script_start = time.time()

    with open(log_path, "w", encoding="utf-8") as log_file:
        probes, hits, discovery_duration = discovery(project_dir, agent_jar, target_package, log_file)

        if discovery_only:
            msg = (
                f"\n[INFO] Discovery done - {len(probes)} probe(s) found.\n"
                f"Artifacts saved in: {target}\n"
            )
            print(msg)
            log_file.write(msg)
            return

        recorded_probes = get_recorded_probes(db_path, resolved_project_name) if ("json" in formats and not redo) else set()
        probes_to_run = {pid: d for pid, d in probes.items() if pid not in recorded_probes}

        if not probes_to_run:
            msg = f"\n[INFO] All {len(probes)} probe(s) already recorded in database. Skipping evaluation.\n"
            print(msg)
            log_file.write(msg)
            return

        if len(probes_to_run) < len(probes):
            skipped = len(probes) - len(probes_to_run)
            msg = f"\n[INFO] Resuming progress: {skipped} skipped, {len(probes_to_run)} left to evaluate.\n"
            print(msg)
            log_file.write(msg)

        # If discovery was slow, evaluations are usually slow too, so we scale timeout from that.
        dynamic_timeout = max(discovery_duration * 2.0, 10.0)
        log_file.write(f"Timeout for evaluations set to: {dynamic_timeout:.2f}s\n")

        def batch_callback(batch_probes):
            # We save every batch so an interrupted run can continue where it stopped.
            if "json" in formats:
                export_json(resolved_project_name, batch_probes, hits, db_path)

        (
            master_probes,
            dashboard_ledger,
            dashboard_methods,
            dashboard_tests,
            test_summary,
            metrics,
            global_tier3_probes,
        ) = run_analysis(probes_to_run, hits, project_dir, agent_jar, target_package,
                         dynamic_timeout, log_file, batch_callback=batch_callback,
                         batch_size=batch_size)

        analytics_text = format_analytics(metrics)
        log_file.write(analytics_text + "\n")

        total_duration = time.time() - script_start
        log_file.write(f"Total wall-clock time: {total_duration:.2f}s\n")
        log_file.write(f"Execution log: {log_path}\n")

        if "stdout" in formats:
            export_stdout(metrics, analytics_text, project_dir, total_duration)

        if "html" in formats:
            export_html(project_dir, dashboard_ledger, dashboard_methods, dashboard_tests,
                        test_summary, metrics, global_tier3_probes, master_probes,
                        no_browser=no_browser)


def run_batch(batch_config_path, agent_jar, formats, db_path, no_browser, batch_size, redo):
    with open(batch_config_path, encoding="utf-8") as batch_file:
        projects = json.load(batch_file)

    batch_start = time.time()

    for project in projects:
        project_name = project.get("name", project["dir"])
        project_dir = project["dir"]
        project_package = project["package"]

        if not os.path.isdir(project_dir):
            print(f"[{project_name}] Directory not found: {project_dir} - skipping.")
            continue

        print(f"\n{'=' * 60}")
        print(f"  Project : {project_name}")
        print(f"  Dir     : {project_dir}")
        print(f"  Package : {project_package}")
        print(f"{'=' * 60}")

        try:
            run_single_project(project_dir, agent_jar, project_package, formats, db_path,
                               discovery_only=False, no_browser=no_browser,
                               project_name=project_name, batch_size=batch_size, redo=redo)
        except SystemExit as exc:
            print(f"[{project_name}] Pipeline exited early: {exc}. Continuing.")
        except Exception as exc:
            print(f"[{project_name}] Unexpected error: {exc}. Continuing.")

    print(f"\nBatch complete in {time.time() - batch_start:.1f}s.")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="main_isolated.py",
        description=(
            "Unified perturbation-testing pipeline.\n\n"
            "Single-project:\n"
            "  python main_isolated.py <project_dir> <agent_jar> <target_package> [options]\n\n"
            "Batch mode:\n"
            "  python main_isolated.py --batch <config.json> <agent_jar> [options]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )



    parser.add_argument("project_dir",    nargs="?", help="Maven project root (single-project mode).")
    parser.add_argument("agent_jar",                 help="Path to the perturbation-agent JAR.")
    parser.add_argument("target_package", nargs="?", help="Java package to instrument (single-project mode).")

    parser.add_argument(
        "--batch", metavar="CONFIG_JSON",
        help="Path to a JSON array of {dir, package, name} project descriptors.",
    )
    parser.add_argument(
        "--format", dest="formats", action="append",
        choices=["stdout", "html", "json"], metavar="FORMAT",
        help="Export format (repeatable): stdout | html | json.  Default: stdout.",
    )

    parser.add_argument(
        "--output", default=DEFAULT_DB_PATH, metavar="DB_FILE",
        help=f"JSON database path (default: {DEFAULT_DB_PATH}). Used with --format json.",
    )

    parser.add_argument(
        "--batch-size", type=int, default=100, metavar="N",
        help="Number of probes to evaluate before saving progress to the database (default: 100).",
    )
    parser.add_argument(
        "--redo", action="store_true",
        help="Force re-evaluation of all probes (ignore already recorded probes).",
    )
    parser.add_argument(
        "--discovery-only", action="store_true",
        help="Run only the discovery phase and exit without evaluation.",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Generate the HTML dashboard but do not open it in a browser.",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    formats = set(args.formats) if args.formats else {"stdout"}

    if not os.path.isfile(args.agent_jar):
        sys.exit(f"Agent JAR not found: {args.agent_jar}")

    if args.batch:
        if not os.path.isfile(args.batch):
            sys.exit(f"Batch config not found: {args.batch}")
        run_batch(args.batch, args.agent_jar, formats, args.output, args.no_browser, args.batch_size, args.redo)
        return

    if not args.project_dir or not args.target_package:
        parser.error(
            "project_dir and target_package are required in single-project mode.\n"
            "Use --batch <config.json> for multi-project runs."
        )

    if not os.path.isdir(args.project_dir):
        sys.exit(f"Project directory not found: {args.project_dir}")

    run_single_project(
        args.project_dir,
        args.agent_jar,
        args.target_package,
        formats,
        args.output,
        args.discovery_only,
        args.no_browser,
        batch_size=args.batch_size,
        redo=args.redo,
    )


if __name__ == "__main__":
    main()
"""
run.py — Unified entry-point for the perturbation-testing pipeline.

Single-project:
    python run.py <project_dir> <agent_jar> <target_package> [options]

Batch mode:
    python run.py --batch <projects.json> <agent_jar> [options]

Options:
    --format  stdout | html | json   repeatable; default: stdout
    --output  <path>                 JSON database path (default: database.json)
    --discovery-only                 stop after discovery, skip evaluation
    --no-browser                     generate the HTML dashboard but do not open it

Examples:
    python run.py ./my-project ./agent.jar org.example --format stdout --format html
    python run.py ./my-project ./agent.jar org.example --format stdout --format html --format json
    python run.py --batch projects.json ./agent.jar --format stdout --format html --format json --no-browser
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from collections import defaultdict

from helper_scripts.probe_analyser import discovery, run_analysis, format_analytics
from helper_scripts.dashboard_builder import generate_dashboard
from helper_scripts.db_exporter import append_to_database, already_recorded


# ==============================================================================
# EXPORT FUNCTIONS
# ==============================================================================

def export_stdout(metrics, analytics_text, project_dir, total_duration):
    """Print the final analytics summary to the terminal."""
    print(analytics_text)
    print(f"Total wall-clock time : {total_duration:.2f}s")
    print(f"Artifacts saved in    : {os.path.join(project_dir, 'target/perturb')}")


def export_html(
    project_dir,
    dashboard_ledger, dashboard_methods, dashboard_tests,
    test_summary, metrics, global_tier3_probes, master_probes,
    no_browser=False,
):
    """Generate the HTML dashboard and optionally open it in a browser."""
    html_file = generate_dashboard(
        project_dir,
        dashboard_ledger, dashboard_methods, dashboard_tests,
        test_summary, metrics, global_tier3_probes, master_probes,
    )
    print(f"Dashboard generated at: {html_file}")
    if not no_browser:
        webbrowser.open('file://' + os.path.realpath(html_file))


def export_json(project_name, master_probes, hits, db_path):
    """Delegate all serialisation to db_exporter — run.py stays schema-free."""
    hit_counts = defaultdict(lambda: defaultdict(int))
    for pid, tests_set in hits.items():
        for t in tests_set:
            hit_counts[pid][t] += 1

    append_to_database(project_name, master_probes, hit_counts, db_path)


# ==============================================================================
# SINGLE-PROJECT PIPELINE
# ==============================================================================

def run_single_project(
    project_dir, agent_jar, target_package,
    formats, db_path, discovery_only, no_browser,
    project_name=None,
):
    """
    Run the full pipeline for one project and dispatch to all requested exports.

    Parameters
    ----------
    project_dir    : str   — Maven project root.
    agent_jar      : str   — path to the perturbation-agent JAR.
    target_package : str   — Java package to instrument.
    formats        : set   — any subset of {'stdout', 'html', 'json'}.
    db_path        : str   — JSON database path (used only when 'json' in formats).
    discovery_only : bool  — stop after discovery, skip evaluation.
    no_browser     : bool  — suppress auto-opening the HTML dashboard.
    project_name   : str   — display name (defaults to the directory basename).
    """
    target = os.path.join(project_dir, "target/perturb")
    os.makedirs(target, exist_ok=True)
    log_path = os.path.join(target, "execution.log")

    p_name = project_name or os.path.basename(os.path.abspath(project_dir))
    script_start = time.time()

    with open(log_path, "w", encoding="utf-8") as log_file:

        # ── Phase 1: Discovery ─────────────────────────────────────────────
        probes, hits, discovery_duration = discovery(
            project_dir, agent_jar, target_package, log_file,
        )

        if discovery_only:
            msg = (
                f"\n[INFO] Discovery done — {len(probes)} probe(s) found.\n"
                f"Artifacts saved in: {target}\n"
            )
            print(msg)
            log_file.write(msg)
            return

        dynamic_timeout = max(discovery_duration * 2.0, 10.0)
        log_file.write(f"Timeout for evaluations set to: {dynamic_timeout:.2f}s\n")

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

        # ── Phase 3: Analytics (always written to log) ────────────────────
        analytics_text = format_analytics(metrics)
        log_file.write(analytics_text + "\n")

        total_duration = time.time() - script_start
        log_file.write(f"Total wall-clock time: {total_duration:.2f}s\n")
        log_file.write(f"Execution log: {log_path}\n")

        # ── Phase 4: Exports ───────────────────────────────────────────────
        if 'stdout' in formats:
            export_stdout(metrics, analytics_text, project_dir, total_duration)

        if 'html' in formats:
            export_html(
                project_dir,
                dashboard_ledger, dashboard_methods, dashboard_tests,
                test_summary, metrics, global_tier3_probes, master_probes,
                no_browser=no_browser,
            )

        if 'json' in formats:
            export_json(p_name, master_probes, hits, db_path)


# ==============================================================================
# BATCH MODE
# ==============================================================================

def run_batch(batch_config_path, agent_jar, formats, db_path, no_browser):
    """
    Run the pipeline for every project in a JSON config file, skipping any
    already present in the database.

    Config format (projects.json):
        [
          { "dir": "/path/to/project", "package": "com.example", "name": "MyProject" },
          ...
        ]
    """
    with open(batch_config_path, encoding="utf-8") as f:
        projects = json.load(f)

    done = already_recorded(db_path) if 'json' in formats else set()
    if done:
        print(
            f"Existing database at '{db_path}' — "
            f"skipping {len(done)} already-recorded project(s): "
            f"{', '.join(sorted(done))}.\n"
            "Delete the file to force a full re-run."
        )

    batch_start = time.time()

    for project in projects:
        p_name = project.get("name", project["dir"])
        p_dir  = project["dir"]
        p_pkg  = project["package"]

        if p_name in done:
            print(f"[{p_name}] Already in database — skipping.")
            continue

        if not os.path.isdir(p_dir):
            print(f"[{p_name}] Directory not found: {p_dir} — skipping.")
            continue

        print(f"\n{'=' * 60}")
        print(f"  Project : {p_name}")
        print(f"  Dir     : {p_dir}")
        print(f"  Package : {p_pkg}")
        print(f"{'=' * 60}")

        try:
            run_single_project(
                p_dir, agent_jar, p_pkg,
                formats, db_path,
                discovery_only=False,
                no_browser=no_browser,
                project_name=p_name,
            )
        except SystemExit as exc:
            print(f"[{p_name}] Pipeline exited early: {exc}. Continuing.")
        except Exception as exc:
            print(f"[{p_name}] Unexpected error: {exc}. Continuing.")

    print(f"\nBatch complete in {time.time() - batch_start:.1f}s.")


# ==============================================================================
# CLI
# ==============================================================================

def build_parser():
    parser = argparse.ArgumentParser(
        prog="run.py",
        description=(
            "Unified perturbation-testing pipeline.\n\n"
            "Single-project:\n"
            "  python run.py <project_dir> <agent_jar> <target_package> [options]\n\n"
            "Batch mode:\n"
            "  python run.py --batch <config.json> <agent_jar> [options]"
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
        "--output", default="database.json", metavar="DB_FILE",
        help="JSON database path (default: database.json). Used with --format json.",
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
        run_batch(args.batch, args.agent_jar, formats, args.output, args.no_browser)
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
    )


if __name__ == "__main__":
    main()
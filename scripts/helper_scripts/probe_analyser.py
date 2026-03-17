import re
import sys
import time
from collections import defaultdict

try:
    from maven_runner import run_maven
    from artifact_reader import (read_probes, read_hits, read_test_outcomes, read_perturbations, )
except ModuleNotFoundError:
    from .maven_runner import run_maven
    from .artifact_reader import (read_probes, read_hits, read_test_outcomes, read_perturbations,)


# ---------------------------------------------------------------------------
# Probe description helpers
# ---------------------------------------------------------------------------

def parse_probe(desc):
    """
    Robustly extract (modification_type, fqcn, method_name) from a probe description.
    """
    parts = desc.rsplit(" in ", 1)
    if len(parts) != 2:
        return "unknown", "unknown", "unknown"

    mod = parts[0].replace("Modified ", "").strip()
    sig = parts[1].strip()

    cm_match = re.search(r'([\w\.\$]+)\.([\w\$<>\-]+)\(', sig)
    if cm_match:
        return mod, cm_match.group(1), cm_match.group(2)

    constructor_match = re.search(r'([\w\.\$]+)\(', sig)
    if constructor_match:
        fqcn = constructor_match.group(1)
        return mod, fqcn, fqcn.split('.')[-1]

    return mod, "unknown", "unknown"


def get_warning(mod, method_name):
    """
    Return a human-readable diagnostic message for a probe that survived.
    """
    mod_lower = mod.lower()
    if "return value" in mod_lower:
        return (
            f"Diagnostic: The return value of <code>{method_name}()</code> was corrupted, "
            "but this test's final assertions were not sensitive to the change. "
            "The state either failed to propagate, or the assertions are too broad."
        )
    elif "argument" in mod_lower:
        return (
            f"Diagnostic: The arguments passed to <code>{method_name}()</code> were corrupted, "
            "but the test remained unaffected. The logic might be ignoring these inputs, "
            "or the state failed to propagate."
        )
    elif "variable" in mod_lower:
        return (
            f"Diagnostic: An internal variable in <code>{method_name}()</code> was modified, "
            "but the test's assertions missed the side-effects. "
            "The infection failed to reach the evaluated state."
        )
    return (
        f"Diagnostic: <code>{method_name}()</code> was perturbed, but the test passed. "
        "The state either failed to propagate, or the assertions are too broad."
    )


# ---------------------------------------------------------------------------
# Discovery phase
# ---------------------------------------------------------------------------

def discovery(project_dir, agent_jar, target_package, log_file):
    """
    Run Maven with probe_id=-1 to enumerate all instrumentation points.

    Returns
    -------
    probes            : dict  int -> description str
    hits              : defaultdict(set)  int -> set of test names
    discovery_duration: float  seconds elapsed
    """
    print("Running Discovery Phase...")
    log_file.write("Running Discovery Phase...\n")
    start_time = time.time()

    code, stderr, _ = run_maven(-1, project_dir, agent_jar, target_package)
    discovery_duration = time.time() - start_time
    log_file.write(f"Discovery finished in {discovery_duration:.2f} seconds.\n")

    if code != 0:
        sys.exit(f"Discovery failed:\n{stderr[-1000:]}")

    raw_probes = read_probes(project_dir)

    # Ghost probe filtering (project-level).
    # The LVT is a compiler-level setting applied globally via Maven's -g flag.
    # If ANY probe has a proper named description, debug info is present throughout.
    # In that case drop:
    #   1. JVM-slot probes ("(JVM slot N)") - compiler ghosts with no name.
    #   2. Probes with no description or unparseable FQCN - registered via
    #      idForLocation but never described by ProbeCatalog (ghost slot inside
    #      a method that has LVT entries for other slots, e.g. "probe 190225529").
    # If NO probe has a proper named description, debug info is globally absent;
    # keep JVM-slot probes as the only available information.
    def _is_named(d):
        desc = d['desc']
        if not desc or re.search(r"\(JVM slot \d+\)", desc):
            return False
        return parse_probe(desc)[1] != "unknown"

    project_has_named = any(_is_named(d) for d in raw_probes.values())

    if project_has_named:
        probes = {pid: data for pid, data in raw_probes.items() if _is_named(data)}
        dropped = len(raw_probes) - len(probes)
        if dropped:
            log_file.write(
                f"Filtered out {dropped} ghost/unnamed probe(s) "
                f"(project has debug info; JVM-slot and undescribed probes excluded).\n"
            )
    else:
        probes = {pid: data for pid, data in raw_probes.items()
                  if parse_probe(data['desc'])[1] != "unknown"}
        log_file.write("No debug info detected - keeping JVM-slot probes as fallback.\n")

    if not probes:
        sys.exit("No probes found.")


    hits = read_hits(project_dir)
    return probes, hits, discovery_duration


# ---------------------------------------------------------------------------
# Probe evaluation
# ---------------------------------------------------------------------------

def evaluate(probe_id, tests, project_dir, agent_jar, target_package,
             timeout_limit, log_file):
    """
    Run Maven for a single probe and classify per-test outcomes.

    Returns
    -------
    test_results_dict : dict test_name -> status str  (None on error)
    passed_count      : int
    failed_count      : int
    is_timeout        : bool
    actions_map       : defaultdict(list) test_name -> [action str]
    """
    code, stderr, timed_out = run_maven(
        probe_id, project_dir, agent_jar, target_package,
        timeout_limit, targeted_tests=tests,
    )

    if timed_out:
        log_file.write(
            f"  - TIMEOUT! Run exceeded {timeout_limit:.2f} seconds.\n"
            "  Result: Discarded (Infinite Loop Detected)\n"
        )
        return {t: "FAIL (TIMEOUT)" for t in tests}, 0, len(tests), True, {}

    outcomes = read_test_outcomes(project_dir)
    if not outcomes:
        log_file.write(f"  No outcomes produced:\n{stderr[-1000:]}\n")
        return None, 0, 0, False, {}

    actions_map = read_perturbations(project_dir)

    test_results_dict = {}
    failed_count = 0
    passed_count = 0

    for test in sorted(tests):
        status = outcomes.get(test, 'MISSING')
        test_results_dict[test] = status

        test_actions = actions_map.get(test, [])
        action_str = f"  ({', '.join(test_actions)})" if test_actions else ""
        log_file.write(f"  - {test}: {status}{action_str}\n")

        if "FAIL" in status.upper():
            failed_count += 1
        elif status.upper() == "PASS":
            passed_count += 1

    total = failed_count + passed_count
    if total > 0:
        log_file.write(
            f"  Tests catching perturbation: "
            f"{failed_count / total * 100:.2f}% ({failed_count}/{total})\n"
        )

    return test_results_dict, passed_count, failed_count, False, actions_map


# ---------------------------------------------------------------------------
# Full analysis loop
# ---------------------------------------------------------------------------

def run_analysis(probes, hits, project_dir, agent_jar, target_package,
                 dynamic_timeout, log_file):
    """
    Iterate over every discovered probe, evaluate it, and aggregate results
    into the data structures required by the dashboard builder.

    Returns
    -------
    master_probes     : dict  probe_id -> probe record
    dashboard_ledger  : list  of probe dicts for the Probe-Centric tab
    dashboard_methods : defaultdict  method_key -> method record (Code-Centric tab)
    dashboard_tests   : defaultdict  test_name -> {probes: [...]}  (Test-Centric tab)
    test_summary      : dict  test_name -> {clean, dirty, survived, vulnerable}
    metrics           : dict  summary counts
    global_tier3_probes: dict  probe_id -> first test that clean-killed it
    """
    master_probes = {}
    for pid, probe_data in sorted(probes.items()):
        probe_desc = probe_data['desc']
        mod, fqcn, m_name = parse_probe(probe_desc)
        master_probes[pid] = {
            'id': pid, 'desc': probe_desc, 'fqcn': fqcn, 'method': m_name,
            'status': 'Un-hit', 'test_outcomes': {},
        }

    dashboard_tests = defaultdict(lambda: {'probes': []})
    dashboard_methods = defaultdict(
        lambda: {'fqcn': '', 'method': '', 'tests': set(), 'probes': []}
    )

    global_tier3_probes = {}   # probe_id -> first test that clean-killed it
    errors_count = skipped_count = 0

    total_probes = len(probes)
    current_probe_idx = 0

    for pid, probe_data in sorted(probes.items()):
        current_probe_idx += 1
        probe_desc = probe_data['desc']
        probe_line = probe_data['line']
        line_info = f" (line {probe_line})" if probe_line > 0 else ""

        print(f"({current_probe_idx}/{total_probes}) Probe {pid}{line_info}: {probe_desc}")
        log_file.write(f"\nProbe {pid}{line_info}: {probe_desc}\n")

        tests = hits.get(pid)
        mp = master_probes[pid]
        fqcn = mp['fqcn']
        m_name = mp['method']
        mod = parse_probe(probe_desc)[0]

        if not tests:
            log_file.write("  SKIP: No tests hit this probe\n")
            skipped_count += 1
            continue

        sorted_tests = sorted(tests)

        test_results_dict, p_count, f_count, is_timeout, actions_map = evaluate(
            pid, tests, project_dir, agent_jar, target_package,
            dynamic_timeout, log_file,
        )

        if is_timeout:
            for t in sorted_tests:
                mp['test_outcomes'][t] = 'timeout'
            mp['status'] = 'TIMEOUT'

            method_key = f"{fqcn}#{m_name}"
            dashboard_methods[method_key]['fqcn'] = fqcn
            dashboard_methods[method_key]['method'] = m_name
            dashboard_methods[method_key]['tests'].update(tests)
            dashboard_methods[method_key]['probes'].append({
                'id': pid, 'desc': probe_desc, 'tests': sorted_tests,
                'actions': ['Infinite Loop / Timeout'],
                'exceptions': ['TIMEOUT: Execution exceeded time limit'],
            })

        elif test_results_dict:
            probe_exceptions = set()
            has_clean = has_dirty = has_survived = False

            for t_name, status in test_results_dict.items():
                s_up = status.upper()
                t_actions = actions_map.get(t_name, [])

                if "FAIL" in s_up:
                    if "ASSERT" in s_up or "COMPARISON" in s_up or "MULTIPLEFAILURES" in s_up:
                        # Clean kill — assertion-level failure
                        mp['test_outcomes'][t_name] = 'clean'
                        has_clean = True
                        if pid not in global_tier3_probes:
                            global_tier3_probes[pid] = t_name
                        dashboard_tests[t_name]['probes'].append({
                            'id': pid, 'desc': probe_desc, 'status': status,
                            'tier': 3, 'actions': t_actions,
                        })
                    else:
                        # Dirty kill — exception-level failure
                        mp['test_outcomes'][t_name] = 'dirty'
                        has_dirty = True
                        clean_exc = (
                            status.replace("FAIL (", "").rstrip(")")
                            if status.startswith("FAIL (") else status
                        )
                        probe_exceptions.add(clean_exc)
                        dashboard_tests[t_name]['probes'].append({
                            'id': pid, 'desc': probe_desc, 'status': status,
                            'tier': 2, 'actions': t_actions,
                        })
                elif "PASS" in s_up:
                    mp['test_outcomes'][t_name] = 'survived'
                    has_survived = True
                    dashboard_tests[t_name]['probes'].append({
                        'id': pid, 'desc': probe_desc, 'status': status,
                        'tier': 1, 'actions': t_actions,
                    })

            # Determine overall probe status
            if has_clean:
                mp['status'] = 'Clean Kill'
            elif has_dirty:
                mp['status'] = 'Dirty Kill'
            elif has_survived:
                mp['status'] = 'Survived'

            # Feed Code-Centric tab for dirty-kill probes
            if has_dirty and not has_clean:
                method_key = f"{fqcn}#{m_name}"
                dashboard_methods[method_key]['fqcn'] = fqcn
                dashboard_methods[method_key]['method'] = m_name
                dashboard_methods[method_key]['tests'].update(tests)
                rep_actions = (
                    actions_map.get(sorted_tests[0], []) if sorted_tests else []
                )
                dashboard_methods[method_key]['probes'].append({
                    'id': pid, 'desc': probe_desc, 'tests': sorted_tests,
                    'actions': rep_actions,
                    'exceptions': sorted(list(probe_exceptions)),
                })
        else:
            errors_count += 1

    # ── Build dashboard_ledger from master_probes ──────────────────────────
    dashboard_ledger = []
    for pid, mp in sorted(master_probes.items(), key=lambda x: -len(x[1]['test_outcomes'])):
        if mp['status'] in ('Survived', 'Clean Kill'):
            tier = 1 if mp['status'] == 'Survived' else 3
            dashboard_ledger.append({
                'id': mp['id'], 'desc': mp['desc'], 'fqcn': mp['fqcn'],
                'method': mp['method'],
                'tests': sorted(mp['test_outcomes'].keys()),
                'tier': tier,
            })

    # ── Absolute probe metrics ─────────────────────────────────────────────
    total_discovered  = len(master_probes)
    total_unhit       = sum(1 for mp in master_probes.values() if mp['status'] == 'Un-hit')
    total_executed    = total_discovered - total_unhit
    clean_kills_count = sum(1 for mp in master_probes.values() if mp['status'] == 'Clean Kill')
    dirty_kills_count = sum(
        1 for mp in master_probes.values() if mp['status'] in ('Dirty Kill', 'TIMEOUT')
    )
    survivals_count   = sum(1 for mp in master_probes.values() if mp['status'] == 'Survived')

    # ── Per-test summary for Test-Centric tab ─────────────────────────────
    test_summary = {}
    for pid, mp in master_probes.items():
        for t_name, outcome in mp['test_outcomes'].items():
            if t_name not in test_summary:
                test_summary[t_name] = {'clean': 0, 'dirty': 0, 'survived': 0}
            key = outcome if outcome in ('clean', 'dirty', 'survived') else 'dirty'
            test_summary[t_name][key] += 1
    for t_name, s in test_summary.items():
        s['vulnerable'] = s['survived'] > 0

    vulnerable_tests_count = sum(1 for s in test_summary.values() if s['vulnerable'])

    metrics = {
        'total_discovered':  total_discovered,
        'total_unhit':       total_unhit,
        'total_executed':    total_executed,
        'clean_kills':       clean_kills_count,
        'dirty_kills':       dirty_kills_count,
        'survivals':         survivals_count,
        'vulnerable_tests':  vulnerable_tests_count,
        'errors':            errors_count,
        'skipped':           skipped_count,
    }

    return (
        master_probes,
        dashboard_ledger,
        dashboard_methods,
        dashboard_tests,
        test_summary,
        metrics,
        global_tier3_probes,
    )


def format_analytics(metrics):
    """Return a formatted analytics block suitable for writing to the log."""
    return f"""
        {'=' * 60}
                         FINAL ANALYTICS
        {'=' * 60}
        Total Probes Discovered : {metrics['total_discovered']}
        Probes Executed         : {metrics['total_executed']}
        Un-hit / Dead Code      : {metrics['total_unhit']}
        Errors (No Outcomes)    : {metrics['errors']}
        {'-' * 60}
        PROBE OUTCOMES:
        Clean Kills             : {metrics['clean_kills']}
        Dirty Kills / Timeouts  : {metrics['dirty_kills']}
        Survived (Vulnerability): {metrics['survivals']}
        {'-' * 60}
        VULNERABLE TESTS        : {metrics['vulnerable_tests']}
        {'=' * 60}
        """
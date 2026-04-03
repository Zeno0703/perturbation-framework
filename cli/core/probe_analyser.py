import re
import sys
import time
from collections import defaultdict

from .maven_runner import run_maven
from .artifact_reader import (
    parse_probe,
    read_hits,
    read_perturbations,
    read_probes,
    read_test_outcomes,
)
from .signature_mapper import generate_signature_map


def get_warning(mod, method_name):
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


def discovery(project_dir, agent_jar, target_package, log_file):
    print("Running Discovery Phase...")
    log_file.write("Running Discovery Phase...\n")
    start_time = time.time()

    try:
        generate_signature_map(project_dir)
    except Exception as exc:
        print(f"Pre-flight mapping failed (falling back to bytecode lines): {exc}")

    code, command_output, _ = run_maven(-1, project_dir, agent_jar, target_package, maven_goal="test")
    discovery_duration = time.time() - start_time
    log_file.write(f"Discovery finished in {discovery_duration:.2f} seconds.\n")

    if code != 0:
        sys.exit(f"Discovery failed:\n{command_output[-1000:]}")

    raw_probes = read_probes(project_dir)

    def _is_named(d):
        desc = d['desc']
        if not desc or re.search(r"\(JVM slot \d+\)", desc):
            return False
        return parse_probe(desc)[1] != "unknown"

    # We only drop JVM-slot probes if this project clearly has real LVT names.
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


def evaluate(probe_id, tests, project_dir, agent_jar, target_package,
             timeout_limit, log_file):
    _, command_output, timed_out = run_maven(
        probe_id, project_dir, agent_jar, target_package,
        timeout_limit, targeted_tests=tests, maven_goal="surefire:test"
    )

    if timed_out:
        log_file.write(
            f"  - TIMEOUT! Run exceeded {timeout_limit:.2f} seconds.\n"
            "  Result: Discarded (Infinite Loop Detected)\n"
        )
        return {t: "FAIL (TIMEOUT)" for t in tests}, 0, len(tests), True, {}

    outcomes = read_test_outcomes(project_dir)
    if not outcomes:
        log_file.write(f"  No outcomes produced:\n{command_output[-1000:]}\n")
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


def run_analysis(probes, hits, project_dir, agent_jar, target_package,
                 dynamic_timeout, log_file, batch_callback=None, batch_size=100):
    master_probes = {}
    for pid, probe_data in sorted(probes.items()):
        probe_desc = probe_data['desc']
        mod, fqcn, m_name, _, _ = parse_probe(probe_desc)
        master_probes[pid] = {
            'id': pid, 'desc': probe_desc, 'fqcn': fqcn, 'method': m_name,
            'status': 'Un-hit', 'test_outcomes': {},
            'line': probe_data.get('line', -1),
            'asmDescriptor': probe_data.get('asmDescriptor', '')
        }

    dashboard_tests = defaultdict(lambda: {'probes': []})
    dashboard_methods = defaultdict(
        lambda: {'fqcn': '', 'method': '', 'tests': set(), 'probes': []}
    )

    global_tier3_probes = {}
    errors_count = skipped_count = 0
    total_probes = len(probes)
    current_probe_idx = 0

    batch_counter = 0
    batch_master_probes = {}

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

        if not tests:
            log_file.write("  SKIP: No tests hit this probe\n")
            skipped_count += 1
            batch_master_probes[pid] = mp
            batch_counter += 1
            # Even skipped probes are flushed in batches so resume data stays complete.
            if batch_callback and batch_counter >= batch_size:
                batch_callback(batch_master_probes)
                batch_master_probes = {}
                batch_counter = 0
            continue

        sorted_tests = sorted(tests)
        # Sorting gives deterministic logs and stable representative-test selection.

        test_results_dict, _, _, is_timeout, actions_map = evaluate(
            pid, tests, project_dir, agent_jar, target_package,
            dynamic_timeout, log_file,
        )

        if is_timeout:
            # Timeout means this probe made tests hang, so we record timeout per touched test.
            for t in sorted_tests:
                mp['test_outcomes'][t] = {'outcome': 'timeout', 'exception': 'TimeoutException'}
            mp['status'] = 'TIMEOUT'

            method_key = f"{fqcn}#{m_name}"
            dashboard_methods[method_key]['fqcn'] = fqcn
            dashboard_methods[method_key]['method'] = m_name
            dashboard_methods[method_key]['tests'].update(tests)
            dashboard_methods[method_key]['probes'].append({
                'id': pid, 'desc': probe_desc, 'tests': sorted_tests,
                'actions': ['Infinite Loop / Timeout'],
                'exceptions': ['TIMEOUT: Execution exceeded time limit'],
                'line': probe_line
            })

        elif test_results_dict:
            probe_exceptions = set()
            has_clean = has_dirty = has_survived = False

            for t_name, status in test_results_dict.items():
                s_up = status.upper()
                t_actions = actions_map.get(t_name, [])

                if "FAIL" in s_up:
                    # Assertion-style failures are counted as clean kills (the test caught the semantic break).
                    if "ASSERT" in s_up or "COMPARISON" in s_up or "MULTIPLEFAILURES" in s_up:
                        mp['test_outcomes'][t_name] = {'outcome': 'clean', 'exception': None}
                        has_clean = True
                        if pid not in global_tier3_probes:
                            global_tier3_probes[pid] = t_name
                        dashboard_tests[t_name]['probes'].append({
                            'id': pid, 'desc': probe_desc, 'status': status,
                            'tier': 3, 'actions': t_actions, 'line': probe_line
                        })
                    else:
                        # Non-assert failures are dirty kills (usually crashes/exceptions).
                        clean_exc = (
                            status.replace("FAIL (", "").rstrip(")")
                            if status.startswith("FAIL (") else status
                        )
                        mp['test_outcomes'][t_name] = {'outcome': 'dirty', 'exception': clean_exc}
                        has_dirty = True
                        probe_exceptions.add(clean_exc)
                        dashboard_tests[t_name]['probes'].append({
                            'id': pid, 'desc': probe_desc, 'status': status,
                            'tier': 2, 'actions': t_actions, 'line': probe_line
                        })
                elif "PASS" in s_up:
                    mp['test_outcomes'][t_name] = {'outcome': 'survived', 'exception': None}
                    has_survived = True
                    dashboard_tests[t_name]['probes'].append({
                        'id': pid, 'desc': probe_desc, 'status': status,
                        'tier': 1, 'actions': t_actions, 'line': probe_line
                    })

            if has_clean:
                mp['status'] = 'Clean Kill'
            elif has_dirty:
                mp['status'] = 'Dirty Kill'
            elif has_survived:
                mp['status'] = 'Survived'

            if has_dirty and not has_clean:
                method_key = f"{fqcn}#{m_name}"
                dashboard_methods[method_key]['fqcn'] = fqcn
                dashboard_methods[method_key]['method'] = m_name
                dashboard_methods[method_key]['tests'].update(tests)
                # For method view we just keep one representative action trace instead of duplicating all traces.
                rep_actions = actions_map.get(sorted_tests[0], []) if sorted_tests else []
                dashboard_methods[method_key]['probes'].append({
                    'id': pid, 'desc': probe_desc, 'tests': sorted_tests,
                    'actions': rep_actions,
                    'exceptions': sorted(list(probe_exceptions)),
                    'line': probe_line
                })
        else:
            errors_count += 1

        batch_master_probes[pid] = mp
        batch_counter += 1
        if batch_callback and batch_counter >= batch_size:
            batch_callback(batch_master_probes)
            batch_master_probes = {}
            batch_counter = 0

    if batch_callback and batch_master_probes:
        batch_callback(batch_master_probes)

    dashboard_ledger = []
    for pid, mp in sorted(master_probes.items(), key=lambda x: -len(x[1]['test_outcomes'])):
        if mp['status'] in ('Survived', 'Clean Kill'):
            tier = 1 if mp['status'] == 'Survived' else 3
            dashboard_ledger.append({
                'id': mp['id'], 'desc': mp['desc'], 'fqcn': mp['fqcn'],
                'method': mp['method'],
                'tests': sorted(mp['test_outcomes'].keys()),
                'tier': tier,
                'line': mp.get('line', -1)
            })

    total_discovered = len(master_probes)
    total_unhit = sum(1 for mp in master_probes.values() if mp['status'] == 'Un-hit')
    total_executed = total_discovered - total_unhit
    clean_kills_count = sum(1 for mp in master_probes.values() if mp['status'] == 'Clean Kill')
    dirty_kills_count = sum(1 for mp in master_probes.values() if mp['status'] == 'Dirty Kill')
    timeouts_count = sum(1 for mp in master_probes.values() if mp['status'] == 'TIMEOUT')
    survivals_count = sum(1 for mp in master_probes.values() if mp['status'] == 'Survived')

    test_summary = {}
    for pid, mp in master_probes.items():
        for t_name, t_data in mp['test_outcomes'].items():
            if t_name not in test_summary:
                test_summary[t_name] = {'clean': 0, 'dirty': 0, 'survived': 0}
            outcome = t_data['outcome']
            # In high-level analytics, timeout behaves like dirty because both are non-clean failures.
            key = outcome if outcome in ('clean', 'dirty', 'survived') else 'dirty'
            test_summary[t_name][key] += 1
    for t_name, s in test_summary.items():
        s['vulnerable'] = s['survived'] > 0

    vulnerable_tests_count = sum(1 for s in test_summary.values() if s['vulnerable'])

    metrics = {
        'total_discovered': total_discovered,
        'total_unhit': total_unhit,
        'total_executed': total_executed,
        'clean_kills': clean_kills_count,
        'dirty_kills': dirty_kills_count,
        'timeouts': timeouts_count,
        'survivals': survivals_count,
        'vulnerable_tests': vulnerable_tests_count,
        'errors': errors_count,
        'skipped': skipped_count,
    }

    return master_probes, dashboard_ledger, dashboard_methods, dashboard_tests, test_summary, metrics, global_tier3_probes


def format_analytics(metrics):
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
        Dirty Kills             : {metrics['dirty_kills']}
        Timeouts                : {metrics['timeouts']}
        Survived (Vulnerability): {metrics['survivals']}
        {'-' * 60}
        VULNERABLE TESTS        : {metrics['vulnerable_tests']}
        {'=' * 60}
        """
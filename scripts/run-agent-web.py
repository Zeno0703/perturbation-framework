import os
import sys
import subprocess
import time
import signal
import webbrowser
import re
import json
from collections import defaultdict

OUT_DIR = "target/perturb"
ARTIFACTS = ("probes.txt", "hits.txt", "test-outcomes.txt", "perturbations.txt")


def clear_artifacts(project_dir):
    target = os.path.join(project_dir, OUT_DIR)
    os.makedirs(target, exist_ok=True)
    for name in ARTIFACTS:
        path = os.path.join(target, name)
        if os.path.exists(path):
            os.remove(path)


def run_maven(probe_id, project_dir, agent_jar, target_package, timeout_limit=None, targeted_tests=None):
    clear_artifacts(project_dir)

    arg_line = (
        f'-javaagent:"{agent_jar}" '
        f'-Dperturb.package={target_package} '
        f'-Dperturb.outDir={OUT_DIR} '
        f'-Dperturb.activeProbe={probe_id} '
        '-Dorg.agent.hidden.bytebuddy.experimental=true'
    )

    command = [
        "mvn", "test",
        f'-DargLine={arg_line}',
        "-Djunit.jupiter.extensions.autodetection.enabled=true",
        "-Djacoco.skip=true"
    ]

    if targeted_tests:
        command.append(f'-Dtest={",".join(targeted_tests)}')

    try:
        process = subprocess.Popen(
            command, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            preexec_fn=os.setsid
        )
        _, stderr = process.communicate(timeout=timeout_limit)
        return process.returncode, stderr, False

    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        return -1, "PROCESS TIMED OUT", True


def unescape(text):
    return text.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t").replace("\\\\", "\\")


def read_artifact(project_dir, filename):
    path = os.path.join(project_dir, OUT_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            result = []
            for line in f:
                if "\t" not in line:
                    continue
                parts = line.rstrip("\r\n").split("\t", 1)
                if len(parts) == 2:
                    result.append([unescape(parts[0]), unescape(parts[1])])
            return result
    except FileNotFoundError:
        return []


def get_java_file_path(project_dir, fqcn, is_test=False):
    if not fqcn or fqcn == "unknown": return None
    base_class = fqcn.split('$')[0]
    rel_path = base_class.replace('.', '/') + ".java"
    base_dir = "src/test/java" if is_test else "src/main/java"
    return os.path.join(project_dir, base_dir, rel_path)


def read_java_file(project_dir, fqcn, is_test=False):
    path = get_java_file_path(project_dir, fqcn, is_test)
    if not path or not os.path.exists(path):
        return f"// Source file not found: {path}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"// Error reading file: {str(e)}"


def discovery(project_dir, agent_jar, target_package):
    print("Running Discovery Phase...")
    start_time = time.time()

    code, stderr, _ = run_maven(-1, project_dir, agent_jar, target_package)
    discovery_duration = time.time() - start_time
    print(f"Discovery finished in {discovery_duration:.2f} seconds.")

    if code != 0:
        sys.exit(f"Discovery failed:\n{stderr[-1000:]}")

    probes = {int(k): v for k, v in read_artifact(project_dir, "probes.txt")}
    if not probes:
        sys.exit("No probes found.")

    hits = defaultdict(set)
    for pid, test in read_artifact(project_dir, "hits.txt"):
        hits[int(pid)].add(test)

    return probes, hits, discovery_duration


def evaluate(probe_id, tests, project_dir, agent_jar, target_package, timeout_limit):
    code, stderr, timed_out = run_maven(probe_id, project_dir, agent_jar, target_package, timeout_limit,
                                        targeted_tests=tests)

    if timed_out:
        print(f"  - TIMEOUT! Run exceeded {timeout_limit:.2f} seconds.\n  Result: Discarded (Infinite Loop Detected)")
        return {t: "FAIL (TIMEOUT)" for t in tests}, 0, len(tests), True, {}

    outcomes = {k: v.strip() for k, v in read_artifact(project_dir, "test-outcomes.txt")}
    if not outcomes:
        print(f"  No outcomes produced:\n{stderr[-1000:]}")
        return None, 0, 0, False, {}

    actions_map = defaultdict(list)
    for test_id, action in read_artifact(project_dir, "perturbations.txt"):
        actions_map[test_id].append(action)

    test_results_dict = {}
    failed_count = 0
    passed_count = 0

    for test in sorted(tests):
        status = outcomes.get(test, 'MISSING')
        test_results_dict[test] = status

        test_actions = actions_map.get(test, [])
        action_str = f"  ({', '.join(test_actions)})" if test_actions else ""
        print(f"  - {test}: {status}{action_str}")

        if "FAIL" in status.upper():
            failed_count += 1
        elif status.upper() == "PASS":
            passed_count += 1

    total = failed_count + passed_count
    if total > 0:
        print(f"  Tests catching perturbation: {failed_count / total * 100:.2f}% ({failed_count}/{total})")

    return test_results_dict, passed_count, failed_count, False, actions_map


def parse_probe(desc):
    match = re.search(r'Modified (.*?) in (.*)', desc)
    if not match: return "unknown", "unknown", "unknown"
    mod = match.group(1)
    sig = match.group(2)

    cm_match = re.search(r'([\w\.\$]+)\.([\w\$]+)\(', sig)
    if cm_match:
        return mod, cm_match.group(1), cm_match.group(2)
    return mod, "unknown", "unknown"


def get_warning(mod, method_name):
    mod_lower = mod.lower()
    if "return value" in mod_lower:
        return f"Diagnostic: The return value of <code>{method_name}()</code> was corrupted, but this test's final assertions were not sensitive to the change. The state either failed to propagate, or the assertions are too broad."
    elif "argument" in mod_lower:
        return f"Diagnostic: The arguments passed to <code>{method_name}()</code> were corrupted, but the test remained unaffected. The logic might be ignoring these inputs, or the state failed to propagate."
    elif "variable" in mod_lower:
        return f"Diagnostic: An internal variable in <code>{method_name}()</code> was modified, but the test's assertions missed the side-effects. The infection failed to reach the evaluated state."
    return f"Diagnostic: <code>{method_name}()</code> was perturbed, but the test passed. The state either failed to propagate, or the assertions are too broad."


def build_action_trace(p):
    action_list = p.get('actions', [])
    if not action_list:
        action_list = ["State modification applied"]

    disp = f"<span class='text-muted'>Execution Trace (Hit {len(action_list)} times):</span><br>"
    disp += "<div class='execution-trace'>"
    for idx, act in enumerate(action_list, 1):
        disp += f"{idx}. {escape_html(act)}<br>"
    disp += "</div>"
    return disp


def to_idea_link(project_dir, fqcn, is_test=False):
    path = get_java_file_path(project_dir, fqcn, is_test)
    if not path: return "#"
    return f"idea://open?file={os.path.abspath(path)}"


def sanitize_id(text):
    return re.sub(r'\W+', '_', text)


def escape_html(text):
    return text.replace('<', '&lt;').replace('>', '&gt;')


def escape_js(text):
    if not text: return ""
    return str(text).replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')


def generate_dashboard(project_dir, dashboard_ledger, dashboard_methods, test_stats, metrics, global_tier3_probes):
    html_path = os.path.join(project_dir, OUT_DIR, "dashboard.html")

    file_cache = {}
    needed_files = set()

    for test_name, stats in test_stats.items():
        test_class = test_name.split('#')[0]
        needed_files.add((test_class, True))
        for p in stats['probes']:
            _, fqcn, _ = parse_probe(p['desc'])
            if fqcn != "unknown":
                needed_files.add((fqcn, False))

    for p in dashboard_ledger:
        if p['fqcn'] and p['fqcn'] != "unknown":
            needed_files.add((p['fqcn'], False))

    for method_key, stats in dashboard_methods.items():
        if stats['fqcn'] and stats['fqcn'] != "unknown":
            needed_files.add((stats['fqcn'], False))

    for fqcn, is_test in needed_files:
        file_cache[fqcn] = read_java_file(project_dir, fqcn, is_test)

    file_cache_json = json.dumps(file_cache).replace("</", "<\\/")

    # ---------------------------------------------------------
    # HTML Builders for Ledger (Probe-Centric - Tab 3)
    # ---------------------------------------------------------
    def build_ledger_row(p):
        class_name = p['fqcn'].split('.')[-1] if p['fqcn'] != 'unknown' else 'Unknown'

        if p['tier'] == 1:
            badge_class = "badge-danger"
            status_text = "Globally Unprotected"
        else:
            badge_class = "badge-success"
            status_text = "Globally Caught"

        witness_list = "".join([f"<li style='margin-bottom: 4px;'>{escape_html(t)}</li>" for t in p['tests']])
        ide_link = to_idea_link(project_dir, p['fqcn'], False)

        return f"""
        <tr id='ledger-row-{p['id']}' class="clickable-row" onclick="toggleRow(event, 'ledger-desc-{p['id']}')">
            <td class="font-medium code-font">#{p['id']}</td>
            <td class="code-font">{class_name}.{p['method']}()</td>
            <td><div class="scrollable-text" style="max-width: 25vw;">{escape_html(p['desc'])}</div></td>
            <td class="text-center">{len(p['tests'])} Tests</td>
            <td class="text-right"><span id="ledger-badge-{p['id']}" class="badge {badge_class}">{status_text}</span></td>
        </tr>
        <tr id="ledger-desc-{p['id']}" class="details-row" style="display: none;">
            <td colspan="5" class="p-0">
                <div class="test-details">
                    <div style="display: flex; gap: 24px; margin-bottom: 0;">
                        <div style="flex: 2; overflow: hidden;">
                            <h4 style="margin-top: 0; font-size: 13px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">Witness List (Footprint)</h4>
                            <ul style="max-height: 150px; overflow-y: auto; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; padding-left: 20px; color: var(--text-main); margin: 0;">
                                {witness_list}
                            </ul>
                        </div>
                        <div style="flex: 1; display: flex; flex-direction: column; justify-content: flex-start; gap: 12px; border-left: 1px solid #e2e8f0; padding-left: 24px;">
                            <h4 style="margin-top: 0; font-size: 13px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">Action Panel</h4>
                            <a href="{ide_link}" class="btn-primary" style="padding: 12px; font-size: 13px; text-align: center; justify-content: center; white-space: normal;">🔗 Open Target in IDE to Write a New Test</a>
                            <button class="btn-small" style="padding: 12px; width: 100%; justify-content: center;" onclick="event.stopPropagation(); openCodeModal('{escape_js(p['fqcn'])}', '{escape_js(p['method'])}', null, null)">View Target Source Code</button>
                        </div>
                    </div>
                </div>
            </td>
        </tr>
        """

    def build_ledger_table(rows_html, tbody_id):
        return f"""
        <div class="table-container" style="margin-top: 16px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <table>
                <thead>
                    <tr>
                        <th style="width: 100px;">Probe ID</th>
                        <th style="width: 250px;">Target Location</th>
                        <th>The Mutation</th>
                        <th class="text-center" style="width: 120px;">Footprint</th>
                        <th class="text-right" style="width: 180px;">Global Status</th>
                    </tr>
                </thead>
                <tbody id="{tbody_id}">
                    {rows_html}
                </tbody>
            </table>
        </div>
        """

    ledger_t1 = []
    ledger_t3 = []

    for p in sorted(dashboard_ledger, key=lambda x: -len(x['tests'])):
        if p['tier'] == 1:
            ledger_t1.append(p)
        elif p['tier'] == 3:
            ledger_t3.append(p)

    ledger_html = ""

    if ledger_t1:
        rows_html = "".join([build_ledger_row(p) for p in ledger_t1])
        ledger_html += f"""
        <div class='details-section'>
            <div class='details-title text-danger accordion-header' onclick="toggleAccordion('content-ledger-t1', 'icon-ledger-t1')">
                <span><span id='icon-ledger-t1' class='accordion-icon'>▼</span> Globally Unprotected <span id='count-ledger-t1'>[{len(ledger_t1)} Probes]</span></span>
            </div>
            <div id='content-ledger-t1' style='display: block;'>
                {build_ledger_table(rows_html, 'tbody-ledger-t1')}
            </div>
        </div>
        """

    ledger_html += f"""
    <div class='details-section' id='section-ledger-pending' style='display: none;'>
        <div class='details-title text-primary accordion-header' onclick="toggleAccordion('content-ledger-pending', 'icon-ledger-pending')">
            <span><span id='icon-ledger-pending' class='accordion-icon'>▼</span> Pending Fix <span id='count-ledger-pending'>[0 Probes]</span></span>
        </div>
        <div id='content-ledger-pending' style='display: block;'>
            {build_ledger_table('', 'tbody-ledger-pending')}
        </div>
    </div>
    """

    if ledger_t3:
        rows_html = "".join([build_ledger_row(p) for p in ledger_t3])
        ledger_html += f"""
        <div class='details-section'>
            <div class='details-title text-success accordion-header' onclick="toggleAccordion('content-ledger-t3', 'icon-ledger-t3')">
                <span><span id='icon-ledger-t3' class='accordion-icon'>▶</span> Globally Caught <span id='count-ledger-t3'>[{len(ledger_t3)} Probes]</span></span>
            </div>
            <div id='content-ledger-t3' style='display: none;'>
                {build_ledger_table(rows_html, 'tbody-ledger-t3')}
            </div>
        </div>
        """

    ledger_html += f"""
    <div class='details-section' id='section-ledger-discarded' style='display: none;'>
        <div class='details-title text-muted accordion-header' onclick="toggleAccordion('content-ledger-discarded', 'icon-ledger-discarded')">
            <span><span id='icon-ledger-discarded' class='accordion-icon'>▶</span> Discarded Noise <span id='count-ledger-discarded'>[0 Probes]</span></span>
        </div>
        <div id='content-ledger-discarded' style='display: none;'>
            {build_ledger_table('', 'tbody-ledger-discarded')}
        </div>
    </div>
    """

    # ---------------------------------------------------------
    # Generate Test-Centric Rows (Tab 1)
    # ---------------------------------------------------------
    valid_sorted_tests = []

    for test_name, stats in sorted(test_stats.items(), key=lambda x: (x[1]['hit'] - x[1]['caught'], x[1]['hit']),
                                   reverse=True):
        t1 = []
        t3 = []
        t_covered = []

        # Strictly filter out Tier 2
        for p in stats['probes']:
            if p['tier'] == 3:
                t3.append(p)
            elif p['id'] in global_tier3_probes:
                p['saviour'] = global_tier3_probes[p['id']]
                t_covered.append(p)
            elif p['tier'] == 1:
                t1.append(p)

        semantic_hits = len(t1) + len(t3) + len(t_covered)
        if semantic_hits == 0:
            continue  # Skip tests that only hit exceptions

        valid_sorted_tests.append((test_name, stats, t1, t3, t_covered, semantic_hits))

    total_tests = len(valid_sorted_tests)
    total_t1_unreviewed = 0
    fully_triaged_tests = 0
    test_rows = ""

    for test_name, stats, t1, t3, t_covered, semantic_hits in valid_sorted_tests:
        safe_id = sanitize_id(test_name)
        unreviewed_count = len(t1)
        total_t1_unreviewed += unreviewed_count

        if unreviewed_count == 0:
            badge_html = f'<span class="status-pill clear">[ Fully Triaged & Clear ]</span>'
            fully_triaged_tests += 1
        else:
            badge_html = f'<span class="status-pill pending">[ {unreviewed_count} Unreviewed ]</span>'

        test_class = test_name.split('#')[0]
        test_method = test_name.split('#')[1] if '#' in test_name else "unknown"
        test_link = to_idea_link(project_dir, test_class, is_test=True)

        display_test_class = test_class.split('.')[-1]
        display_test_name = f"{display_test_class}.{test_method}()" if test_method != "unknown" else display_test_class

        inner_html = f"<div class='test-details'>"

        # 1. Survived (Tier 1)
        if t1:
            inner_html += f"""
            <div class='details-section'>
                <div class='details-title text-danger accordion-header' onclick="toggleAccordion('content-t1-{safe_id}', 'icon-t1-{safe_id}')">
                    <span><span id='icon-t1-{safe_id}' class='accordion-icon'>▼</span> Survived (Failed to Catch) <span id='count-t1-{safe_id}'>[{len(t1)} Probes]</span></span>
                </div>
                <div id='content-t1-{safe_id}' style='display: block;'>
                    <ul class='details-list' id='list-t1-{safe_id}'>
            """
            for p in t1:
                mod, fqcn, m_name = parse_probe(p['desc'])
                target_link = to_idea_link(project_dir, fqcn, is_test=False)
                action_disp = build_action_trace(p)

                inner_html += f"""
                        <li id='probe-{safe_id}-{p['id']}' data-probe-id='{p['id']}' data-test-id='{safe_id}' data-tier='1' data-state='unreviewed' class='probe-item' style='border-left-color: var(--danger);'>
                            <div class='probe-meta'>
                                <span class='probe-id'>Probe {p['id']}</span>
                                <div class='action-group'>
                                    <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(test_class)}', '{escape_js(test_method)}', '{escape_js(fqcn)}', '{escape_js(m_name)}')">View Source Code</button>
                                    <a href="{target_link}" class="btn-small">Open Target</a>
                                    <a href="{test_link}" class="btn-small">Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                            """
                warn = get_warning(mod, m_name)
                inner_html += f"<div class='probe-warning'>{warn}</div>"
                inner_html += f"""
                            <div class='triage-actions' id='actions-{safe_id}-{p['id']}'>
                                <button class='btn-triage btn-action' title='This test should catch this. It failed because my inputs are weak (Logical Masking) or my assertions are missing (Missing Oracle).' onclick="triageTest('{safe_id}', '{p['id']}', 'action', 'Weak Test')">Weak Test</button>
                                <button class='btn-triage btn-noise' title='This perturbation is inherently unobservable (e.g., Math.abs()). No input will ever catch this. It is a false positive generated by the tool.' onclick="triageTest('{safe_id}', '{p['id']}', 'equivalent', 'Equivalent')">Equivalent</button>
                                <button class='btn-triage btn-noise' title='This specific test is not the right place to catch this. (Covers both Architectural Scope and Test Setup Masking).' onclick="triageTest('{safe_id}', '{p['id']}', 'noise', 'Out of Scope')">Out of Scope</button>
                            </div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        # 3. Action Required (Cascaded)
        inner_html += f"""
        <div class='details-section' id='cascaded-section-{safe_id}' style='display: none;'>
            <div class='details-title text-orange accordion-header' onclick="toggleAccordion('content-cascaded-{safe_id}', 'icon-cascaded-{safe_id}')">
                <span><span id='icon-cascaded-{safe_id}' class='accordion-icon'>▶</span> Action Required (Identified in Another Test) <span id='count-cascaded-{safe_id}'>[0 Probes]</span></span>
            </div>
            <div id='content-cascaded-{safe_id}' style='display: none;'>
                <ul id='list-cascaded-{safe_id}' class='details-list'></ul>
            </div>
        </div>
        """

        # 4. Covered by Another Test
        if t_covered:
            inner_html += f"""
            <div class='details-section'>
                <div class='details-title text-info accordion-header' onclick="toggleAccordion('content-tc-{safe_id}', 'icon-tc-{safe_id}')">
                    <span><span id='icon-tc-{safe_id}' class='accordion-icon'>▶</span> Covered by Another Test <span id='count-tc-{safe_id}'>[{len(t_covered)} Probes]</span></span>
                </div>
                <div id='content-tc-{safe_id}' style='display: none;'>
                    <ul class='details-list'>
            """
            for p in t_covered:
                mod, fqcn, m_name = parse_probe(p['desc'])
                target_link = to_idea_link(project_dir, fqcn, is_test=False)
                action_disp = build_action_trace(p)

                saviour_test = p.get('saviour', 'Another Test')
                saviour_class = saviour_test.split('#')[0]
                saviour_method = saviour_test.split('#')[1] if '#' in saviour_test else "unknown"

                inner_html += f"""
                        <li class='probe-item' style='border-left-color: var(--info); background-color: #f8fafc;'>
                            <div class='probe-meta'>
                                <span class='probe-id'>Probe {p['id']}</span>
                                <div class='action-group'>
                                    <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(test_class)}', '{escape_js(test_method)}', '{escape_js(fqcn)}', '{escape_js(m_name)}')">View Source Code</button>
                                    <a href="{target_link}" class="btn-small">Open Target</a>
                                    <a href="{test_link}" class="btn-small">Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                            <div class='saviour-box'>
                                <span class='text-muted font-medium'>Safely caught by:</span> <a href="#" onclick="event.stopPropagation(); openCodeModal('{escape_js(saviour_class)}', '{escape_js(saviour_method)}', null, null); return false;" class="saviour-link">{escape_html(saviour_test)}</a>
                            </div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        # 5. Semantic Failures
        if t3:
            inner_html += f"""
            <div class='details-section'>
                <div class='details-title text-success accordion-header' onclick="toggleAccordion('content-t3-{safe_id}', 'icon-t3-{safe_id}')">
                    <span><span id='icon-t3-{safe_id}' class='accordion-icon'>▶</span> Semantic Failures (Clean Kills) <span id='count-t3-{safe_id}'>[{len(t3)} Probes]</span></span>
                </div>
                <div id='content-t3-{safe_id}' style='display: none;'>
                    <ul class='details-list'>
            """
            for p in t3:
                mod, fqcn, m_name = parse_probe(p['desc'])
                target_link = to_idea_link(project_dir, fqcn, is_test=False)
                action_disp = build_action_trace(p)

                inner_html += f"""
                        <li class='probe-item' style='border-left-color: var(--success);'>
                            <div class='probe-meta'>
                                <span class='probe-id'>Probe {p['id']}</span>
                                <div class='action-group'>
                                    <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(test_class)}', '{escape_js(test_method)}', '{escape_js(fqcn)}', '{escape_js(m_name)}')">View Source Code</button>
                                    <a href="{target_link}" class="btn-small">Open Target</a>
                                    <a href="{test_link}" class="btn-small">Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        # 6. Filtered Noise Archive
        inner_html += f"""
        <div class='details-section' id='noise-section-{safe_id}' style='display: none;'>
            <div class='details-title text-muted accordion-header' onclick="toggleAccordion('content-noise-{safe_id}', 'icon-noise-{safe_id}')">
                <span><span id='icon-noise-{safe_id}' class='accordion-icon'>▶</span> Filtered Noise <span id='count-noise-{safe_id}'>[0 Probes]</span></span>
            </div>
            <div id='content-noise-{safe_id}' style='display: none;'>
                <ul id='list-noise-{safe_id}' class='details-list'></ul>
            </div>
        </div>
        </div>
        """

        test_rows += f"""
        <tr class="clickable-row" onclick="toggleRow(event, 'desc-{safe_id}')">
            <td class="font-medium text-main">
                <div style="display: flex; justify-content: space-between; align-items: center; gap: 20px;">
                    <div class="scrollable-text code-font" style="font-weight: 600;">{display_test_name}</div>
                    <span class="expand-hint" style="flex-shrink: 0;">Show details ▼</span>
                </div>
            </td>
            <td class="text-center">{semantic_hits}</td>
            <td id="badge-{safe_id}" class="text-right">{badge_html}</td>
        </tr>
        <tr id="desc-{safe_id}" class="details-row" style="display: none;">
            <td colspan="3" class="p-0">{inner_html}</td>
        </tr>
        """

    # ---------------------------------------------------------
    # Generate Code-Centric Rows (Tab 2)
    # ---------------------------------------------------------
    code_rows = ""
    valid_methods_count = 0
    total_t2_unreviewed = 0

    for method_key, stats in sorted(dashboard_methods.items(), key=lambda x: -len(x[1]['probes'])):
        if not stats['probes']:
            continue

        valid_methods_count += 1
        safe_m_id = sanitize_id(method_key)
        m_fqcn = stats['fqcn']
        m_name = stats['method']
        c_name = m_fqcn.split('.')[-1] if m_fqcn != 'unknown' else 'Unknown'
        total_t2_unreviewed += len(stats['probes'])

        inner_code_html = f"""
        <div class='details-section'>
            <div class='details-title text-warning accordion-header' onclick="toggleAccordion('content-code-t2-{safe_m_id}', 'icon-code-t2-{safe_m_id}')">
                <span><span id='icon-code-t2-{safe_m_id}' class='accordion-icon'>▼</span> Execution Crashes <span id='count-code-t2-{safe_m_id}'>[{len(stats['probes'])} Probes]</span></span>
            </div>
            <div id='content-code-t2-{safe_m_id}' style='display: block;'>
                <ul class='details-list' id='list-code-t2-{safe_m_id}'>
        """
        for p in stats['probes']:
            witness_list = ", ".join(p['tests'])
            action_disp = build_action_trace(p)
            inner_code_html += f"""
            <li id='code-probe-{p['id']}' class='probe-item' style='border-left-color: var(--warning);'>
                <div class='probe-meta'>
                    <span class='probe-id'>Probe {p['id']}</span>
                    <div class='action-group'>
                        <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(m_fqcn)}', '{escape_js(m_name)}', null, null)">View Target Source Code</button>
                    </div>
                </div>
                <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                <div class='perturb-action'>{action_disp}</div>
                <div style='margin-top: 12px; font-size: 12px; color: var(--text-muted); background: #f8fafc; padding: 8px 12px; border-radius: 6px; border: 1px solid #e2e8f0;'>
                    <strong>Witnessed by {len(p['tests'])} Tests:</strong> <span style="font-family: ui-monospace, SFMono-Regular, monospace;">{escape_html(witness_list)}</span>
                </div>
                <div class='triage-actions' id='code-actions-{p['id']}'>
                    <button class='btn-triage btn-action' title='The code lacks defensive checks. I will add an if (x == null) to the production code.' onclick="triageCode('{safe_m_id}', '{p['id']}', 'action-code', 'Brittle Code')">Brittle Code</button>
                    <button class='btn-triage btn-noise' title='This state can mathematically never happen in the real app. The tool hallucinated it.' onclick="triageCode('{safe_m_id}', '{p['id']}', 'equivalent-code', 'Impossible State')">Impossible State</button>
                </div>
            </li>
            """
        inner_code_html += "</ul></div></div>"

        # Code-Centric Archive
        inner_code_html += f"""
        <div class='details-section' id='code-noise-section-{safe_m_id}' style='display: none;'>
            <div class='details-title text-muted accordion-header' onclick="toggleAccordion('content-code-noise-{safe_m_id}', 'icon-code-noise-{safe_m_id}')">
                <span><span id='icon-code-noise-{safe_m_id}' class='accordion-icon'>▶</span> Filtered Noise (Impossible States) <span id='count-code-noise-{safe_m_id}'>[0 Probes]</span></span>
            </div>
            <div id='content-code-noise-{safe_m_id}' style='display: none;'>
                <ul id='list-code-noise-{safe_m_id}' class='details-list'></ul>
            </div>
        </div>
        """

        code_rows += f"""
        <tr class="clickable-row" onclick="toggleRow(event, 'code-desc-{safe_m_id}')">
            <td class="font-medium text-main">
                <div style="display: flex; justify-content: space-between; align-items: center; gap: 20px;">
                    <div class="scrollable-text code-font">{c_name}.{m_name}()</div>
                    <span class="expand-hint" style="flex-shrink: 0;">Show details ▼</span>
                </div>
            </td>
            <td class="text-center font-medium text-warning">{len(stats['probes'])} Crashes</td>
            <td id="code-badge-{safe_m_id}" class="text-right">
                <span class="status-pill pending">[ {len(stats['probes'])} Unreviewed ]</span>
            </td>
        </tr>
        <tr id="code-desc-{safe_m_id}" class="details-row" style="display: none;">
            <td colspan="3" class="p-0">
                <div class="test-details" style="padding-top: 16px;">{inner_code_html}</div>
            </td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Perturbation Analysis Dashboard</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github.min.css">
        <style>
            :root {{
                --bg-main: #f8fafc;
                --bg-card: #ffffff;
                --text-main: #0f172a;
                --text-muted: #64748b;
                --border-color: #cbd5e1;
                --danger: #ef4444;
                --danger-bg: #fef2f2;
                --danger-text: #991b1b;
                --warning: #f59e0b;
                --warning-bg: #fffbeb;
                --warning-text: #92400e;
                --success: #10b981;
                --success-bg: #ecfdf5;
                --success-text: #065f46;
                --info: #0ea5e9;
                --info-bg: #f0f9ff;
                --info-text: #0369a1;
                --orange: #ea580c;
                --orange-bg: #ffedd5;
                --primary: #3b82f6;
            }}
            body {{
                font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background-color: var(--bg-main);
                color: var(--text-main);
                margin: 0;
                padding: 32px 0;
                line-height: 1.5;
            }}
            .container {{ width: 100%; padding: 0 32px; box-sizing: border-box; }}
            h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 32px; color: var(--text-main); letter-spacing: -0.02em; }}

            .metrics-container {{ display: none; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 32px; }}
            .metrics-container.active {{ display: grid; }}

            .metric-card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; text-align: center; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05); }}
            .metric-value {{ font-size: 36px; font-weight: 700; color: var(--text-main); line-height: 1.1; margin-bottom: 4px; letter-spacing: -0.02em; }}
            .metric-label {{ font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}

            .tabs {{ display: flex; border-bottom: 2px solid #e2e8f0; margin-bottom: 24px; gap: 32px; }}
            .tab {{ padding: 12px 0; font-size: 14px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s ease; }}
            .tab:hover {{ color: var(--text-main); }}
            .tab.active {{ color: var(--primary); border-bottom-color: var(--primary); }}
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; }}

            .tab-header {{ margin-bottom: 24px; }}
            .tab-header h2 {{ font-size: 20px; font-weight: 600; margin: 0 0 4px 0; color: var(--text-main); letter-spacing: -0.01em; }}
            .tab-header p {{ margin: 0; color: var(--text-muted); font-size: 14px; }}

            .table-container {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
            table {{ width: 100%; table-layout: fixed; border-collapse: collapse; text-align: left; }}
            th, td {{ padding: 16px 20px; border-bottom: 1px solid var(--border-color); font-size: 14px; overflow: hidden; text-overflow: ellipsis; }}
            th {{ background-color: #f8fafc; font-weight: 700; color: #475569; text-transform: uppercase; font-size: 12px; letter-spacing: 0.05em; border-bottom: 2px solid #e2e8f0; }}

            .text-center {{ text-align: center; }}
            .text-right {{ text-align: right; }}
            .font-medium {{ font-weight: 500; }}
            .code-font {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px; font-weight: 600; color: var(--text-main); }}
            .p-0 {{ padding: 0 !important; }}

            .scrollable-text {{ display: block; width: 100%; overflow-x: auto; white-space: nowrap; padding-bottom: 4px; scrollbar-width: none; }}
            .scrollable-text::-webkit-scrollbar {{ display: none; }}
            .scrollable-text:hover::-webkit-scrollbar {{ display: block; height: 6px; }}
            .scrollable-text::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 3px; }}

            .badge {{ display: inline-flex; align-items: center; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; line-height: 1.5; white-space: nowrap; box-shadow: inset 0 0 0 1px rgba(0,0,0,0.05); }}
            .badge-danger {{ background-color: var(--danger-bg); color: var(--danger-text); }}
            .badge-warning {{ background-color: var(--warning-bg); color: var(--warning-text); }}
            .badge-success {{ background-color: var(--success-bg); color: var(--success-text); }}
            .badge-primary {{ background-color: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }}

            .text-danger {{ color: var(--danger) !important; border-bottom-color: var(--danger) !important; }}
            .text-warning {{ color: var(--warning) !important; border-bottom-color: var(--warning) !important; }}
            .text-success {{ color: var(--success) !important; border-bottom-color: var(--success) !important; }}
            .text-info {{ color: var(--info) !important; border-bottom-color: var(--info) !important; }}
            .text-orange {{ color: var(--orange) !important; border-bottom-color: var(--orange) !important; }}
            .text-muted {{ color: var(--text-muted) !important; border-bottom-color: var(--text-muted) !important; }}
            .text-primary {{ color: var(--primary) !important; border-bottom-color: var(--primary) !important; }}
            .text-main {{ color: var(--text-main); }}

            .clickable-row {{ cursor: pointer; transition: background-color 0.2s; }}
            .clickable-row:hover {{ background-color: #f1f5f9; }}
            .expand-hint {{ font-size: 12px; color: var(--text-muted); font-weight: 600; transition: color 0.2s; }}
            .clickable-row:hover .expand-hint {{ color: var(--primary); }}

            .details-row {{ background-color: #f8fafc; box-shadow: inset 0 4px 8px -4px rgba(0, 0, 0, 0.05), inset 0 -4px 8px -4px rgba(0, 0, 0, 0.05); }} 
            .test-details {{ padding: 32px 24px; }}

            .details-section {{ margin-bottom: 32px; }}
            .details-section:last-child {{ margin-bottom: 0; }}
            .details-title {{ font-size: 14px; font-weight: 700; border-bottom: 2px solid; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }}

            .accordion-header {{ cursor: pointer; user-select: none; transition: opacity 0.2s; display: flex; align-items: center; }}
            .accordion-header:hover {{ opacity: 0.7; }}
            .accordion-icon {{ display: inline-block; width: 20px; font-size: 12px; }}

            .details-list {{ list-style: none; padding: 0; margin: 16px 0 0 0; display: flex; flex-direction: column; gap: 16px; }}

            .probe-item {{ background: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid #cbd5e1; border-radius: 8px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px -2px rgba(0, 0, 0, 0.02); display: flex; flex-direction: column; transition: all 0.2s ease; }}
            .probe-item:hover {{ box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.03); }}

            .probe-meta {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; font-size: 13px; }}
            .probe-id {{ font-weight: 700; color: var(--text-main); font-size: 15px; }}
            .probe-desc {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px; color: var(--text-main); margin-bottom: 12px; background: #f8fafc; padding: 10px 14px; border-radius: 6px; border: 1px solid #e2e8f0; }}
            .probe-warning {{ background-color: var(--danger-bg); color: var(--danger-text); padding: 12px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; margin-top: 12px; border-left: 4px solid var(--danger); }}

            .perturb-action {{ font-size: 13px; margin-top: 4px; display: inline-block; color: var(--text-main); width: 100%; }}
            .execution-trace {{ max-height: 100px; overflow-y: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; margin-top: 8px; padding: 8px 12px; background: #f8fafc; border-left: 3px solid #cbd5e1; border-radius: 0 4px 4px 0; }}

            .saviour-box {{ margin-top: 16px; font-size: 13px; padding: 12px 16px; background-color: #ffffff; border-radius: 6px; border-left: 4px solid var(--info); box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; border-left-width: 4px; }}
            .saviour-link {{ font-family: ui-monospace, SFMono-Regular, monospace; font-weight: 600; text-decoration: none; color: var(--primary); cursor: pointer; transition: color 0.2s; }}
            .saviour-link:hover {{ color: var(--text-main); text-decoration: underline; }}

            .action-group {{ display: flex; align-items: center; gap: 8px; margin-left: auto; flex-wrap: nowrap; }}

            .btn-small {{ display: inline-flex; align-items: center; background-color: #ffffff; color: var(--text-main); border: 1px solid #cbd5e1; text-decoration: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; transition: all 0.2s ease-in-out; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,0.02); white-space: nowrap; }}
            .btn-small:hover {{ background-color: #f1f5f9; border-color: #94a3b8; color: var(--primary); text-decoration: none; }}

            .btn-primary {{ display: inline-flex; align-items: center; background-color: var(--primary); color: #ffffff; border: none; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 600; transition: all 0.2s ease-in-out; cursor: pointer; box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3); white-space: nowrap; }}
            .btn-primary:hover {{ background-color: #2563eb; color: #ffffff; text-decoration: none; }}

            .triage-actions {{ margin: 20px -20px -20px -20px; padding: 14px 20px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; border-radius: 0 0 8px 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
            .btn-triage {{ padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; transition: all 0.2s; border: 1px solid transparent; background: transparent; }}
            .btn-action {{ color: var(--danger); border-color: #fca5a5; background: #ffffff; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
            .btn-action:hover {{ background: var(--danger-bg); border-color: var(--danger); }}
            .btn-noise {{ color: var(--text-muted); border-color: #cbd5e1; background: #ffffff; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
            .btn-noise:hover {{ background: #f1f5f9; color: var(--text-main); border-color: #94a3b8; }}

            .cascaded-item {{ border-left: 4px solid var(--orange) !important; box-shadow: 0 0 0 1px var(--orange-bg) !important; }}
            .action-required {{ border-left: 4px solid var(--danger) !important; box-shadow: 0 0 0 1px var(--danger-bg); }}
            .noise-item {{ opacity: 0.6; border-left: 4px solid #cbd5e1 !important; }}

            .triage-tag {{ display: inline-block; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 12px; box-shadow: inset 0 0 0 1px rgba(0,0,0,0.05); }}
            .tag-action {{ background: var(--danger-bg); color: var(--danger-text); border: 1px solid #fecaca; }}
            .tag-cascaded {{ background: var(--orange-bg); color: var(--orange); border: 1px solid #fdba74; }}
            .tag-noise {{ background: #f1f5f9; color: var(--text-muted); border: 1px solid #cbd5e1; }}

            .status-pill {{ display: inline-block; padding: 6px 14px; border-radius: 12px; font-size: 12px; font-weight: 600; white-space: nowrap; box-shadow: inset 0 0 0 1px rgba(0,0,0,0.05); }}
            .status-pill.clear {{ background: var(--success-bg); color: var(--success-text); border: 1px solid #a7f3d0; }}
            .status-pill.action {{ background: var(--danger-bg); color: var(--danger-text); border: 1px solid #fecaca; }}
            .status-pill.mid {{ background: var(--warning-bg); color: var(--warning-text); border: 1px solid #fde68a; }}
            .status-pill.pending {{ background: #ffffff; color: var(--text-muted); border: 1px solid #cbd5e1; }}

            /* Modal Styles */
            .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(15, 23, 42, 0.7); backdrop-filter: blur(4px); }}
            .modal-content {{ background-color: #ffffff; margin: 2% auto; padding: 24px; border: 1px solid #cbd5e1; width: 94%; height: 85%; border-radius: 16px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); display: flex; flex-direction: column; }}
            .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
            .modal-header h2 {{ margin: 0; font-size: 20px; color: var(--text-main); font-weight: 700; }}
            .close {{ color: var(--text-muted); font-size: 28px; font-weight: bold; cursor: pointer; transition: color 0.2s; line-height: 1; margin-top: -4px; }}
            .close:hover {{ color: var(--text-main); }}

            .split-view {{ display: flex; gap: 20px; height: 100%; overflow: hidden; }}
            .split-pane {{ flex: 1; display: flex; flex-direction: column; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #f8fafc; transition: all 0.3s ease; box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.02); }}
            .split-pane h3 {{ margin: 0; padding: 14px 20px; background: #ffffff; border-bottom: 1px solid #e2e8f0; font-size: 13px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); z-index: 10; }}
            .pane-subtitle {{ font-weight: 500; color: var(--primary); font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

            .code-container {{ flex: 1; overflow: auto; background: #ffffff; padding: 20px; }}
            .code-container pre {{ margin: 0; }}
            .code-container code {{ font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace; font-size: 13px; line-height: 1.6; }}
            mark.scroll-target {{ background-color: #fef08a; color: #854d0e; border-radius: 3px; padding: 2px 4px; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }}
        </style>
        <script>
            const fileCache = {file_cache_json};
            window.initialT1Count = {total_t1_unreviewed};
            window.initialT2Count = {total_t2_unreviewed};
            window.totalTestCount = {total_tests};
            window.totalMethodCount = {valid_methods_count};

            function switchTab(tabId) {{
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.metrics-container').forEach(m => m.classList.remove('active'));

                document.getElementById(tabId).classList.add('active');
                if (window.event && window.event.currentTarget) {{
                    window.event.currentTarget.classList.add('active');
                }}

                if (tabId === 'test-view') {{
                    document.getElementById('metrics-test').classList.add('active');
                }} else if (tabId === 'probe-view') {{
                    document.getElementById('metrics-probe').classList.add('active');
                }} else if (tabId === 'code-view') {{
                    document.getElementById('metrics-code').classList.add('active');
                }}
            }}

            function toggleRow(event, rowId) {{
                if (event.target.tagName.toLowerCase() === 'a' || event.target.tagName.toLowerCase() === 'button') return;
                var row = document.getElementById(rowId);
                var isHidden = row.style.display === "none";
                row.style.display = isHidden ? "table-row" : "none";

                var hintText = document.querySelector(`tr[onclick="toggleRow(event, '${{rowId}}')"] .expand-hint`);
                if (hintText) {{
                    hintText.innerText = isHidden ? "Hide details ▲" : "Show details ▼";
                }}
            }}

            function toggleAccordion(contentId, iconId) {{
                var content = document.getElementById(contentId);
                var icon = document.getElementById(iconId);
                if (content.style.display === "none") {{
                    content.style.display = "block";
                    icon.innerText = "▼";
                }} else {{
                    content.style.display = "none";
                    icon.innerText = "▶";
                }}
            }}

            function triageTest(testId, probeId, decisionType, tagText) {{
                const probeEl = document.getElementById(`probe-${{testId}}-${{probeId}}`);
                const actionsContainer = document.getElementById(`actions-${{testId}}-${{probeId}}`);

                let tagClass = 'tag-noise';
                if (decisionType === 'action') tagClass = 'tag-action';

                actionsContainer.innerHTML = `<span class="triage-tag ${{tagClass}}">[ ${{tagText}} ]</span>`;
                probeEl.setAttribute('data-state', decisionType);

                if (decisionType === 'action') {{
                    probeEl.classList.add('action-required');

                    // SMART CASCADING across Tests
                    const otherProbes = document.querySelectorAll(`li[data-probe-id="${{probeId}}"][data-state="unreviewed"]`);
                    otherProbes.forEach(otherProbeEl => {{
                        if (otherProbeEl.id.startsWith('code-probe-')) return;

                        if (otherProbeEl.id !== probeEl.id) {{
                            const otherTestId = otherProbeEl.getAttribute('data-test-id');
                            const otherActionsContainer = document.getElementById(`actions-${{otherTestId}}-${{probeId}}`);

                            if(otherActionsContainer) {{
                                otherActionsContainer.innerHTML = `<span class="triage-tag tag-cascaded">[ ${{tagText}} (Cascaded) ]</span>`;
                                otherProbeEl.setAttribute('data-state', 'action');
                                otherProbeEl.classList.add('cascaded-item');

                                const cascadedList = document.getElementById(`list-cascaded-${{otherTestId}}`);
                                const cascadedContainer = document.getElementById(`cascaded-section-${{otherTestId}}`);
                                if(cascadedContainer) cascadedContainer.style.display = 'block';
                                if(cascadedList) cascadedList.appendChild(otherProbeEl);

                                updateBadge(otherTestId);
                                updateAccordionCounts(otherTestId);
                            }}
                        }}
                    }});

                    // CROSS-TAB SYNC: Move the item to "Pending Fix" in the Vulnerability Ledger
                    const ledgerRow = document.getElementById(`ledger-row-${{probeId}}`);
                    const ledgerDesc = document.getElementById(`ledger-desc-${{probeId}}`);
                    if (ledgerRow && ledgerDesc) {{
                        const pendingTbody = document.getElementById('tbody-ledger-pending');
                        const pendingSection = document.getElementById('section-ledger-pending');
                        if (pendingTbody && pendingSection) {{
                            pendingSection.style.display = 'block';
                            pendingTbody.appendChild(ledgerRow);
                            pendingTbody.appendChild(ledgerDesc);

                            const ledgerBadge = document.getElementById(`ledger-badge-${{probeId}}`);
                            if (ledgerBadge) {{
                                ledgerBadge.className = 'badge badge-primary';
                                ledgerBadge.innerText = 'Pending Fix';
                            }}
                            updateLedgerCounts();
                        }}
                    }}

                }} else if (decisionType === 'equivalent') {{
                    probeEl.classList.add('noise-item');
                    const noiseList = document.getElementById(`list-noise-${{testId}}`);
                    const noiseContainer = document.getElementById(`noise-section-${{testId}}`);
                    if(noiseContainer) noiseContainer.style.display = 'block';
                    if(noiseList) noiseList.appendChild(probeEl);

                    // SMART CASCADING across Tests for Equivalent (Global Trash)
                    const otherProbes = document.querySelectorAll(`li[data-probe-id="${{probeId}}"][data-state="unreviewed"]`);
                    otherProbes.forEach(otherProbeEl => {{
                        if (otherProbeEl.id.startsWith('code-probe-')) return;

                        if (otherProbeEl.id !== probeEl.id) {{
                            const otherTestId = otherProbeEl.getAttribute('data-test-id');
                            const otherActionsContainer = document.getElementById(`actions-${{otherTestId}}-${{probeId}}`);

                            if(otherActionsContainer) {{
                                otherActionsContainer.innerHTML = `<span class="triage-tag tag-noise">[ ${{tagText}} (Cascaded) ]</span>`;
                                otherProbeEl.setAttribute('data-state', 'equivalent');
                                otherProbeEl.classList.add('noise-item');

                                const otherNoiseList = document.getElementById(`list-noise-${{otherTestId}}`);
                                const otherNoiseContainer = document.getElementById(`noise-section-${{otherTestId}}`);
                                if(otherNoiseContainer) otherNoiseContainer.style.display = 'block';
                                if(otherNoiseList) otherNoiseList.appendChild(otherProbeEl);

                                updateBadge(otherTestId);
                                updateAccordionCounts(otherTestId);
                            }}
                        }}
                    }});

                    // CROSS-TAB SYNC: Move the item to "Discarded Noise" in the Vulnerability Ledger
                    const ledgerRow = document.getElementById(`ledger-row-${{probeId}}`);
                    const ledgerDesc = document.getElementById(`ledger-desc-${{probeId}}`);
                    if (ledgerRow && ledgerDesc) {{
                        const discardedTbody = document.getElementById('tbody-ledger-discarded');
                        const discardedSection = document.getElementById('section-ledger-discarded');
                        if (discardedTbody && discardedSection) {{
                            discardedSection.style.display = 'block';
                            discardedTbody.appendChild(ledgerRow);
                            discardedTbody.appendChild(ledgerDesc);

                            const ledgerBadge = document.getElementById(`ledger-badge-${{probeId}}`);
                            if (ledgerBadge) {{
                                ledgerBadge.className = 'badge';
                                ledgerBadge.style.backgroundColor = '#e2e8f0';
                                ledgerBadge.style.color = '#475569';
                                ledgerBadge.style.border = '1px solid #cbd5e1';
                                ledgerBadge.innerText = 'Discarded Noise';
                            }}
                            updateLedgerCounts();
                        }}
                    }}

                }} else if (decisionType === 'noise') {{
                    // Out of scope is Local only!
                    probeEl.classList.add('noise-item');
                    const noiseList = document.getElementById(`list-noise-${{testId}}`);
                    const noiseContainer = document.getElementById(`noise-section-${{testId}}`);
                    if(noiseContainer) noiseContainer.style.display = 'block';
                    if(noiseList) noiseList.appendChild(probeEl);
                }}

                updateBadge(testId);
                updateAccordionCounts(testId);
            }}

            function triageCode(methodId, probeId, decisionType, tagText) {{
                const actionsContainer = document.getElementById(`code-actions-${{probeId}}`);
                let tagClass = decisionType === 'action-code' ? 'tag-action' : 'tag-noise';
                actionsContainer.innerHTML = `<span class="triage-tag ${{tagClass}}">[ ${{tagText}} ]</span>`;

                const codeProbeEl = document.getElementById(`code-probe-${{probeId}}`);
                if(codeProbeEl) {{
                    codeProbeEl.setAttribute('data-state', decisionType);

                    if (decisionType === 'action-code') {{
                        codeProbeEl.classList.add('action-required');
                        codeProbeEl.classList.remove('noise-item');
                    }} else if (decisionType === 'equivalent-code') {{
                        codeProbeEl.classList.add('noise-item');
                        codeProbeEl.classList.remove('action-required');

                        // Move to Local Noise List inside Code-Centric tab
                        const noiseList = document.getElementById(`list-code-noise-${{methodId}}`);
                        const noiseContainer = document.getElementById(`code-noise-section-${{methodId}}`);
                        if(noiseContainer) noiseContainer.style.display = 'block';
                        if(noiseList) noiseList.appendChild(codeProbeEl);
                    }}
                }}

                updateCodeAccordionCounts(methodId);
                updateCodeBadge(methodId);
            }}

            function updateCodeAccordionCounts(methodId) {{
                const listT2 = document.getElementById(`list-code-t2-${{methodId}}`);
                if (listT2) {{
                    const count = listT2.querySelectorAll('li').length;
                    const header = document.getElementById(`count-code-t2-${{methodId}}`);
                    if (header) header.innerText = `[${{count}} Probes]`;
                }}
                const listNoise = document.getElementById(`list-code-noise-${{methodId}}`);
                if (listNoise) {{
                    const count = listNoise.querySelectorAll('li').length;
                    const header = document.getElementById(`count-code-noise-${{methodId}}`);
                    if (header) header.innerText = `[${{count}} Probes]`;
                }}
            }}

            function updateCodeBadge(methodId) {{
                const methodContainer = document.getElementById(`code-desc-${{methodId}}`);
                if(!methodContainer) return;

                const total = methodContainer.querySelectorAll('li.probe-item').length;
                const triaged = methodContainer.querySelectorAll('li.probe-item[data-state]').length;
                const unreviewed = total - triaged;
                const needsAction = methodContainer.querySelectorAll('li.probe-item[data-state="action-code"]').length;

                const badgeEl = document.getElementById(`code-badge-${{methodId}}`);

                if (unreviewed === 0 && needsAction === 0) {{
                    badgeEl.innerHTML = `<span class="status-pill clear">[ Fully Triaged & Clear ]</span>`;
                }} else if (unreviewed === 0 && needsAction > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill action">[ Fully Triaged | ${{needsAction}} Need Action ]</span>`;
                }} else if (unreviewed > 0 && needsAction > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill mid">[ ${{unreviewed}} Unreviewed | ${{needsAction}} Need Action ]</span>`;
                }} else {{
                    badgeEl.innerHTML = `<span class="status-pill pending">[ ${{unreviewed}} Unreviewed ]</span>`;
                }}

                // Update Code Global Metrics
                const t2UnreviewedGlobal = document.querySelectorAll('#code-view li.probe-item:not([data-state])').length;
                const t2ActionGlobal = document.querySelectorAll('#code-view li.probe-item[data-state="action-code"]').length;
                const t2NoiseGlobal = document.querySelectorAll('#code-view li.probe-item[data-state="equivalent-code"]').length;
                const fullyTriagedGlobal = document.querySelectorAll('#code-view .status-pill.clear, #code-view .status-pill.action').length;

                const uiT2Inbox = document.getElementById('ui-t2-inbox');
                if(uiT2Inbox) uiT2Inbox.innerText = t2UnreviewedGlobal + ' / ' + window.initialT2Count;

                const uiT2Action = document.getElementById('ui-t2-action');
                if(uiT2Action) uiT2Action.innerText = t2ActionGlobal;

                const uiT2Noise = document.getElementById('ui-t2-noise');
                if(uiT2Noise) uiT2Noise.innerText = t2NoiseGlobal;

                const uiTriagedMethods = document.getElementById('ui-triaged-methods');
                if(uiTriagedMethods) uiTriagedMethods.innerText = fullyTriagedGlobal + ' / ' + window.totalMethodCount;
            }}

            function updateLedgerCounts() {{
                const sections = ['t1', 't3', 'pending', 'discarded'];
                sections.forEach(sec => {{
                    const tbody = document.getElementById(`tbody-ledger-${{sec}}`);
                    const countSpan = document.getElementById(`count-ledger-${{sec}}`);
                    if (tbody && countSpan) {{
                        const count = tbody.children.length / 2; // Each probe has 2 TRs (main + desc)
                        countSpan.innerText = `[${{count}} Probes]`;
                    }}
                }});
            }}

            function updateAccordionCounts(testId) {{
                const listT1 = document.getElementById(`list-t1-${{testId}}`);
                if (listT1) {{
                    const count = listT1.querySelectorAll('li').length;
                    const header = document.getElementById(`count-t1-${{testId}}`);
                    if (header) header.innerText = `[${{count}} Probes]`;
                }}

                const listCascaded = document.getElementById(`list-cascaded-${{testId}}`);
                if (listCascaded) {{
                    const count = listCascaded.querySelectorAll('li').length;
                    const header = document.getElementById(`count-cascaded-${{testId}}`);
                    if (header) header.innerText = `[${{count}} Probes]`;
                }}

                const listNoise = document.getElementById(`list-noise-${{testId}}`);
                if (listNoise) {{
                    const count = listNoise.querySelectorAll('li').length;
                    const header = document.getElementById(`count-noise-${{testId}}`);
                    if (header) header.innerText = `[${{count}} Probes]`;
                }}
            }}

            function updateBadge(testId) {{
                const testContainer = document.getElementById(`desc-${{testId}}`);
                const unreviewed = testContainer.querySelectorAll('li[data-state="unreviewed"]').length;
                const needsAction = testContainer.querySelectorAll('li[data-state="action"]').length;

                const badgeEl = document.getElementById(`badge-${{testId}}`);

                if (unreviewed === 0 && needsAction === 0) {{
                    badgeEl.innerHTML = `<span class="status-pill clear">[ Fully Triaged & Clear ]</span>`;
                }} else if (unreviewed === 0 && needsAction > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill action">[ Fully Triaged | ${{needsAction}} Need Action ]</span>`;
                }} else if (unreviewed > 0 && needsAction > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill mid">[ ${{unreviewed}} Unreviewed | ${{needsAction}} Need Action ]</span>`;
                }} else {{
                    badgeEl.innerHTML = `<span class="status-pill pending">[ ${{unreviewed}} Unreviewed ]</span>`;
                }}

                updateGlobalMetrics();
            }}

            function updateGlobalMetrics() {{
                const t1Unreviewed = document.querySelectorAll('#test-view li[data-tier="1"]:not([data-state])').length;
                const confirmedBugs = document.querySelectorAll('#test-view .tag-action, #test-view .tag-cascaded').length;
                const noiseBugs = document.querySelectorAll('#test-view li.noise-item[data-state="equivalent"]').length;
                const fullyTriaged = document.querySelectorAll('#test-view .status-pill.clear, #test-view .status-pill.action').length;

                const inboxEl = document.getElementById('ui-t1-inbox');
                if(inboxEl) inboxEl.innerText = t1Unreviewed + ' / ' + window.initialT1Count;

                const actionEl = document.getElementById('ui-t1-action');
                if(actionEl) actionEl.innerText = confirmedBugs;

                const noiseEl = document.getElementById('ui-t1-noise');
                if(noiseEl) noiseEl.innerText = noiseBugs;

                const triagedEl = document.getElementById('ui-triaged-tests');
                if(triagedEl) triagedEl.innerText = fullyTriaged + ' / ' + window.totalTestCount;
            }}

            function openCodeModal(class1, method1, class2, method2) {{
                const targetPane = document.getElementById('modalTargetPane');

                if (class2 && class2 !== 'null') {{
                    document.getElementById('modalTestTitle').innerHTML = 'Test Class <span class="pane-subtitle">— ' + class1 + '.' + method1 + '()</span>';
                    document.getElementById('modalTargetTitle').innerHTML = 'Target Class <span class="pane-subtitle">— ' + class2 + '.' + method2 + '()</span>';

                    targetPane.style.display = 'flex';
                    renderAndHighlight('modalTargetCode', fileCache[class2], method2);
                }} else {{
                    document.getElementById('modalTestTitle').innerHTML = 'Source Code <span class="pane-subtitle">— ' + class1 + '.' + method1 + '()</span>';
                    targetPane.style.display = 'none';
                }}

                renderAndHighlight('modalTestCode', fileCache[class1], method1);

                document.getElementById('codeModal').style.display = "block";
                document.body.style.overflow = "hidden";
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Perturbation Analysis Dashboard</h1>

            <div id="metrics-test" class="metrics-container active">
                <div class="metric-card">
                    <div class="metric-value" id="ui-t1-inbox">{total_t1_unreviewed} / {total_t1_unreviewed}</div>
                    <div class="metric-label">Critical Survivals (PASS)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-t1-action">0</div>
                    <div class="metric-label">Confirmed Vulnerabilities</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-t1-noise">0</div>
                    <div class="metric-label">Discarded Noise</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-triaged-tests">{fully_triaged_tests} / {total_tests}</div>
                    <div class="metric-label">Fully Triaged Tests</div>
                </div>
            </div>

            <div id="metrics-probe" class="metrics-container">
                <div class="metric-card">
                    <div class="metric-value">{metrics['evaluated']}</div>
                    <div class="metric-label">Dynamic Targets Executed</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['score']:.2f}%</div>
                    <div class="metric-label">Fault Detection Rate</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['clean_kill']:.2f}%</div>
                    <div class="metric-label">Assertion Adequacy</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['brittle']}</div>
                    <div class="metric-label">Brittle Executions</div>
                </div>
            </div>

            <div id="metrics-code" class="metrics-container">
                <div class="metric-card">
                    <div class="metric-value" id="ui-t2-inbox">{total_t2_unreviewed} / {total_t2_unreviewed}</div>
                    <div class="metric-label">Unreviewed Crashes</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-t2-action">0</div>
                    <div class="metric-label">Brittle Code Found</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-t2-noise">0</div>
                    <div class="metric-label">Impossible States</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-triaged-methods">0 / {valid_methods_count}</div>
                    <div class="metric-label">Fully Triaged Methods</div>
                </div>
            </div>

            <div class="tabs">
                <div class="tab active" onclick="switchTab('test-view')">Test Quality (Test-Centric)</div>
                <div class="tab" onclick="switchTab('probe-view')">Vulnerability Ledger (Probe-Centric)</div>
                <div class="tab" onclick="switchTab('code-view')">Robustness Radar (Code-Centric)</div>
            </div>

            <div id="test-view" class="tab-content active">
                <div class="tab-header">
                    <h2>Test Triage Dashboard</h2>
                    <p>Click on any test row to expand and triage unresolved perturbations. Deep-links will open the classes directly in your IDE.</p>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Test Name</th>
                                <th class="text-center" style="width: 160px;">Probes Executed</th>
                                <th class="text-right" style="width: 280px;">Triage Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {test_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <div id="probe-view" class="tab-content">
                <div class="tab-header">
                    <h2>Vulnerability Ledger (Probe-Centric)</h2>
                    <p>The global status of every injected fault. Discover completely unprotected probes to write brand new unit tests.</p>
                </div>
                <div class="test-details" style="padding: 16px 0;">
                    {ledger_html}
                </div>
            </div>

            <div id="code-view" class="tab-content">
                <div class="tab-header">
                    <h2>Robustness Radar (Code-Centric)</h2>
                    <p>Make production code defensive against illegal states. Grouped by target method, strictly showing Execution Crashes (Tier 2).</p>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Target Method</th>
                                <th class="text-center" style="width: 160px;">Execution Failures</th>
                                <th class="text-right" style="width: 280px;">Triage Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {code_rows}
                        </tbody>
                    </table>
                </div>
            </div>

        </div>

        <div id="codeModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Source Code View</h2>
                    <span class="close" onclick="closeModal()">&times;</span>
                </div>
                <div class="split-view">
                    <div class="split-pane" id="modalTestPane">
                        <h3 id="modalTestTitle">Source Code</h3>
                        <div id="modalTestCode" class="code-container"></div>
                    </div>
                    <div class="split-pane" id="modalTargetPane">
                        <h3 id="modalTargetTitle">Target Class</h3>
                        <div id="modalTargetCode" class="code-container"></div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/java.min.js"></script>
        <script>
            function closeModal() {{
                document.getElementById('codeModal').style.display = "none";
                document.body.style.overflow = "auto";
            }}

            function renderAndHighlight(containerId, code, methodName) {{
                const container = document.getElementById(containerId);
                if (!code) {{
                    container.innerHTML = "<pre><code>// File content not available or could not be read.</code></pre>";
                    return;
                }}

                let escapedCode = code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                container.innerHTML = `<pre><code class="language-java">${{escapedCode}}</code></pre>`;

                hljs.highlightElement(container.querySelector('code'));

                // Regex uses positive lookahead (?=\\s*\\() to ensure we only highlight method calls 
                // and skip highlighting generic words like 'of' or 'get' in comments.
                if (methodName && methodName !== 'unknown' && methodName !== '<init>') {{
                    const codeEl = container.querySelector('code');
                    const regex = new RegExp("(\\\\b" + methodName + "\\\\b)(?=(?:<[^>]+>)*\\\\s*\\\\()", "g");
                    codeEl.innerHTML = codeEl.innerHTML.replace(regex, "<mark class='scroll-target'>$1</mark>");

                    setTimeout(() => {{
                        const targets = container.querySelectorAll('.scroll-target');
                        if (targets.length > 0) {{
                            targets[0].scrollIntoView({{ behavior: 'auto', block: 'center' }});
                        }}
                    }}, 150);
                }}
            }}

            window.onclick = function(event) {{
                const modal = document.getElementById('codeModal');
                if (event.target == modal) {{
                    closeModal();
                }}
            }}

            document.addEventListener('keydown', function(event) {{
                if (event.key === "Escape") {{
                    closeModal();
                }}
            }});
        </script>
    </body>
    </html>
    """

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return html_path


def main():
    if len(sys.argv) != 4:
        sys.exit("Usage: python3 run-agent.py <project_dir> <agent_jar> <target_package>")

    script_start = time.time()
    project_dir, agent_jar, target_package = sys.argv[1:4]

    probes, hits, discovery_duration = discovery(project_dir, agent_jar, target_package)
    dynamic_timeout = max(discovery_duration * 2.0, 10.0)
    print(f"Set strict timeout limit for evaluations: {dynamic_timeout:.2f} seconds")

    tier1_survived = 0
    tier2_error = 0
    tier3_assert = 0
    timeouts_count = skipped_count = errors_count = unknown_errors = 0
    global_tests_passed = 0
    global_tests_failed = 0

    dashboard_tests = defaultdict(lambda: {'hit': 0, 'caught': 0, 'probes': []})
    dashboard_methods = defaultdict(lambda: {'fqcn': '', 'method': '', 'tests': set(), 'probes': []})
    dashboard_ledger = []

    global_tier3_probes = {}

    for pid, probe_desc in sorted(probes.items()):
        print(f"\nProbe {pid}: {probe_desc}")
        tests = hits.get(pid)

        if not tests:
            print("  SKIP: No tests hit this probe")
            skipped_count += 1
            continue

        mod, fqcn, m_name = parse_probe(probe_desc)

        test_results_dict, p_count, f_count, is_timeout, actions_map = evaluate(pid, tests, project_dir, agent_jar,
                                                                                target_package, dynamic_timeout)

        for t in tests:
            dashboard_tests[t]['hit'] += 1

        best_tier = 1

        if is_timeout:
            timeouts_count += 1
            tier2_error += 1
            global_tests_failed += len(tests)
            best_tier = 2

            method_key = f"{fqcn}#{m_name}"
            dashboard_methods[method_key]['fqcn'] = fqcn
            dashboard_methods[method_key]['method'] = m_name
            dashboard_methods[method_key]['tests'].update(tests)
            dashboard_methods[method_key]['probes'].append({
                'id': pid, 'desc': probe_desc, 'tests': sorted(list(tests)), 'status': 'FAIL (TIMEOUT)',
                'actions': ['Infinite Loop / Timeout']
            })
        elif test_results_dict:
            global_tests_passed += p_count
            global_tests_failed += f_count

            has_assert = False
            has_exception = False
            has_pass = False

            for t_name, status in test_results_dict.items():
                s_up = status.upper()
                t_tier = 1

                if "FAIL" in s_up:
                    if "ASSERT" in s_up or "COMPARISON" in s_up or "MULTIPLEFAILURES" in s_up:
                        has_assert = True
                        t_tier = 3
                        dashboard_tests[t_name]['caught'] += 1
                        if pid not in global_tier3_probes:
                            global_tier3_probes[pid] = t_name
                    else:
                        has_exception = True
                        t_tier = 2
                elif "PASS" in s_up:
                    has_pass = True

                t_actions = actions_map.get(t_name, [])

                # Exclude Tier 2 from Tab 1 Inbox
                if t_tier != 2:
                    dashboard_tests[t_name]['probes'].append({
                        'id': pid, 'desc': probe_desc, 'status': status, 'tier': t_tier, 'actions': t_actions
                    })

            if has_assert:
                tier3_assert += 1
                best_tier = 3
            elif has_exception:
                tier2_error += 1
                best_tier = 2

                method_key = f"{fqcn}#{m_name}"
                dashboard_methods[method_key]['fqcn'] = fqcn
                dashboard_methods[method_key]['method'] = m_name
                dashboard_methods[method_key]['tests'].update(tests)

                # Fetch actions for the first test as a representative trace
                rep_test = sorted(list(tests))[0] if tests else None
                rep_actions = actions_map.get(rep_test, []) if rep_test else []

                dashboard_methods[method_key]['probes'].append({
                    'id': pid, 'desc': probe_desc, 'tests': sorted(list(tests)), 'actions': rep_actions
                })
            elif has_pass:
                tier1_survived += 1
                best_tier = 1
            else:
                unknown_errors += 1
        else:
            errors_count += 1

        if not is_timeout and test_results_dict and best_tier != 2:
            dashboard_ledger.append({
                'id': pid,
                'desc': probe_desc,
                'fqcn': fqcn,
                'method': m_name,
                'tests': sorted(list(tests)),
                'tier': best_tier
            })

    total_duration = time.time() - script_start
    total_scored = tier1_survived + tier2_error + tier3_assert
    total_tests_executed = global_tests_passed + global_tests_failed

    perturbation_score = ((tier2_error + tier3_assert) / total_scored * 100) if total_scored > 0 else 0.0
    clean_kill_ratio = (tier3_assert / total_scored * 100) if total_scored > 0 else 0.0
    unified_test_fail_rate = (global_tests_failed / total_tests_executed * 100) if total_tests_executed > 0 else 0.0

    print(f"""
        {'=' * 60}
                         FINAL ANALYTICS
        {'=' * 60}
        Total Probes Discovered : {len(probes)}
        Probes Evaluated        : {total_scored}
        Probes Skipped (No Hit) : {skipped_count}
        Errors (No Outcomes)    : {errors_count + unknown_errors}
        {'-' * 60}
        PERTURBATION RESOLUTION TIERS:
        Tier 1 (PASS)           : {tier1_survived} (Perturbation Survived)
        Tier 2 (FAIL Exception) : {tier2_error} (Execution Error / Timeout)
        Tier 3 (FAIL Assert)    : {tier3_assert} (Semantic Failure)
        {'-' * 60}
        TEST EXECUTION METRICS:
        Total Tests Executed    : {total_tests_executed}
        Tests Passed            : {global_tests_passed}
        Tests Failed            : {global_tests_failed}
        Unified Test Fail Rate  : {unified_test_fail_rate:.2f}%
        {'-' * 60}
        Overall Perturbation Score : {perturbation_score:.2f}% (Tiers 2 & 3)
        Clean Kill Ratio           : {clean_kill_ratio:.2f}% (Tier 3 only)
        {'=' * 60}
        """)

    metrics = {
        'score': perturbation_score,
        'clean_kill': clean_kill_ratio,
        'fail_rate': unified_test_fail_rate,
        'evaluated': total_scored,
        'brittle': tier2_error
    }

    html_file = generate_dashboard(project_dir, dashboard_ledger, dashboard_methods, dashboard_tests, metrics,
                                   global_tier3_probes)
    print(f"\nDashboard generated at: {html_file}")

    webbrowser.open('file://' + os.path.realpath(html_file))


if __name__ == "__main__":
    main()
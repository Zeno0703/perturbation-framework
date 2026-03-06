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


def generate_dashboard(project_dir, probes_data, test_stats, metrics, global_tier3_probes):
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

    for fqcn, is_test in needed_files:
        file_cache[fqcn] = read_java_file(project_dir, fqcn, is_test)

    file_cache_json = json.dumps(file_cache)

    sorted_tests = sorted(
        test_stats.items(),
        key=lambda x: (x[1]['hit'] - x[1]['caught'], x[1]['hit']),
        reverse=True
    )

    probe_rows = ""
    for p in probes_data:
        badge_class = "badge-danger" if p['tier'].startswith("Tier 1") else (
            "badge-warning" if p['tier'].startswith("Tier 2") else "badge-success")
        probe_rows += f"""
        <tr>
            <td class="code-font">{p['id']}</td>
            <td><div class="scrollable-text">{escape_html(p['desc'])}</div></td>
            <td><span class="badge {badge_class}">{p['tier']}</span></td>
            <td class="text-right">{p['catch_rate']}</td>
        </tr>
        """

    test_rows = ""
    total_tests = len(sorted_tests)
    total_t1_unreviewed = 0
    total_t2_unreviewed = 0
    fully_triaged_tests = 0
    fsi_sum = 0  # Re-added the accumulator

    for test_name, stats in sorted_tests:
        hit = stats['hit']
        caught = stats['caught']
        missed = hit - caught
        fsi = (missed / hit * 100) if hit > 0 else 0  # Re-added FSI calculation
        fsi_sum += fsi  # Accumulate the FSI
        safe_id = sanitize_id(test_name)

        t1 = []
        t2 = []
        t3 = []
        t_covered = []

        # Partition probes with Global Awareness
        for p in stats['probes']:
            if p['tier'] == 3:
                t3.append(p)
            elif p['id'] in global_tier3_probes:
                p['saviour'] = global_tier3_probes[p['id']]
                t_covered.append(p)
            elif p['tier'] == 1:
                t1.append(p)
            elif p['tier'] == 2:
                t2.append(p)

        unreviewed_count = len(t1) + len(t2)
        total_t1_unreviewed += len(t1)
        total_t2_unreviewed += len(t2)

        if unreviewed_count == 0:
            badge_html = f'<span class="status-pill clear">[ Fully Triaged & Clear ]</span>'
            fully_triaged_tests += 1
        else:
            badge_html = f'<span class="status-pill pending">[ {unreviewed_count} Unreviewed ]</span>'

        test_class = test_name.split('#')[0]
        test_method = test_name.split('#')[1] if '#' in test_name else "unknown"
        test_link = to_idea_link(project_dir, test_class, is_test=True)

        inner_html = f"<div class='test-details'>"

        # 1. Survived (Tier 1) - Default Expanded
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
                                    <button class='btn-small' onclick="openCodeModal('{test_class}', '{test_method}', '{fqcn}', '{m_name}')">View Source Code</button>
                                    <a href='{target_link}' class='btn-small'>Open Target</a>
                                    <a href='{test_link}' class='btn-small'>Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                            """
                warn = get_warning(mod, m_name)
                inner_html += f"<div class='probe-warning'>{warn}</div>"
                inner_html += f"""
                            <div class='triage-actions' id='actions-{safe_id}-{p['id']}'>
                                <button class='btn-triage btn-action' onclick="triage('{safe_id}', '{p['id']}', 'action', 'Missing Oracle')">Missing Oracle</button>
                                <button class='btn-triage btn-noise' onclick="triage('{safe_id}', '{p['id']}', 'noise', 'Equivalent')">Equivalent</button>
                                <button class='btn-triage btn-noise' onclick="triage('{safe_id}', '{p['id']}', 'noise', 'Blocked / Reassigned')">Blocked / Reassigned</button>
                                <button class='btn-triage btn-noise' onclick="triage('{safe_id}', '{p['id']}', 'noise', 'Out of Scope')">Out of Scope</button>
                            </div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        # 2. Execution Errors (Tier 2) - Default Expanded
        if t2:
            inner_html += f"""
            <div class='details-section'>
                <div class='details-title text-warning accordion-header' onclick="toggleAccordion('content-t2-{safe_id}', 'icon-t2-{safe_id}')">
                    <span><span id='icon-t2-{safe_id}' class='accordion-icon'>▼</span> Execution Errors (Dirty Kills) <span id='count-t2-{safe_id}'>[{len(t2)} Probes]</span></span>
                </div>
                <div id='content-t2-{safe_id}' style='display: block;'>
                    <ul class='details-list' id='list-t2-{safe_id}'>
            """
            for p in t2:
                mod, fqcn, m_name = parse_probe(p['desc'])
                target_link = to_idea_link(project_dir, fqcn, is_test=False)
                action_disp = build_action_trace(p)

                inner_html += f"""
                        <li id='probe-{safe_id}-{p['id']}' data-probe-id='{p['id']}' data-test-id='{safe_id}' data-tier='2' data-state='unreviewed' class='probe-item' style='border-left-color: var(--warning);'>
                            <div class='probe-meta'>
                                <span class='probe-id'>Probe {p['id']}</span>
                                <div class='action-group'>
                                    <button class='btn-small' onclick="openCodeModal('{test_class}', '{test_method}', '{fqcn}', '{m_name}')">View Source Code</button>
                                    <a href='{target_link}' class='btn-small'>Open Target</a>
                                    <a href='{test_link}' class='btn-small'>Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>

                            <div class='triage-actions' id='actions-{safe_id}-{p['id']}'>
                                <button class='btn-triage btn-action' onclick="triage('{safe_id}', '{p['id']}', 'action', 'Brittle Code')">Brittle Code</button>
                                <button class='btn-triage btn-noise' onclick="triage('{safe_id}', '{p['id']}', 'noise', 'Impossible State')">Impossible State</button>
                            </div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        # 3. Action Required (Cascaded) - Default Hidden (Orange styling)
        inner_html += f"""
        <div class='details-section' id='cascaded-section-{safe_id}' style='display: none;'>
            <div class='details-title text-orange accordion-header' style='border-bottom-color: #fdba74;' onclick="toggleAccordion('content-cascaded-{safe_id}', 'icon-cascaded-{safe_id}')">
                <span><span id='icon-cascaded-{safe_id}' class='accordion-icon'>▶</span> Action Required (Identified in Another Test) <span id='count-cascaded-{safe_id}'>[0 Probes]</span></span>
            </div>
            <div id='content-cascaded-{safe_id}' style='display: none;'>
                <ul id='list-cascaded-{safe_id}' class='details-list'></ul>
            </div>
        </div>
        """

        # 4. Covered by Another Test - Default Collapsed
        if t_covered:
            inner_html += f"""
            <div class='details-section'>
                <div class='details-title text-info accordion-header' onclick="toggleAccordion('content-tc-{safe_id}', 'icon-tc-{safe_id}')">
                    <span><span id='icon-tc-{safe_id}' class='accordion-icon'>▶</span> Covered by Another Test [{len(t_covered)} Probes]</span>
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
                                    <button class='btn-small' onclick="openCodeModal('{test_class}', '{test_method}', '{fqcn}', '{m_name}')">View Source Code</button>
                                    <a href='{target_link}' class='btn-small'>Open Target</a>
                                    <a href='{test_link}' class='btn-small'>Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                            <div class='saviour-box'>
                                <span class='text-muted font-medium'>Safely caught by:</span> <a href='#' onclick="openCodeModal('{saviour_class}', '{saviour_method}', null, null); return false;" class='saviour-link'>{escape_html(saviour_test)}</a>
                            </div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        # 5. Semantic Failures (Tier 3) - Default Collapsed
        if t3:
            inner_html += f"""
            <div class='details-section'>
                <div class='details-title text-success accordion-header' onclick="toggleAccordion('content-t3-{safe_id}', 'icon-t3-{safe_id}')">
                    <span><span id='icon-t3-{safe_id}' class='accordion-icon'>▶</span> Semantic Failures (Clean Kills) [{len(t3)} Probes]</span>
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
                                    <button class='btn-small' onclick="openCodeModal('{test_class}', '{test_method}', '{fqcn}', '{m_name}')">View Source Code</button>
                                    <a href='{target_link}' class='btn-small'>Open Target</a>
                                    <a href='{test_link}' class='btn-small'>Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        # 6. Filtered Noise Archive - Default Collapsed
        inner_html += f"""
        <div class='details-section' id='noise-section-{safe_id}' style='display: none;'>
            <div class='details-title text-muted accordion-header' onclick="toggleAccordion('content-noise-{safe_id}', 'icon-noise-{safe_id}')">
                <span><span id='icon-noise-{safe_id}' class='accordion-icon'>▶</span> Filtered Noise (The Archive) <span id='count-noise-{safe_id}'>[0 Probes]</span></span>
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
                    <div class="scrollable-text" style="font-weight: 600;">{test_name}</div>
                    <span class="expand-hint" style="flex-shrink: 0;">Show details ▼</span>
                </div>
            </td>
            <td class="text-center">{hit}</td>
            <td id="badge-{safe_id}" class="text-right">{badge_html}</td>
        </tr>
        <tr id="desc-{safe_id}" class="details-row" style="display: none;">
            <td colspan="3" class="p-0">{inner_html}</td>
        </tr>
        """

    avg_fsi = fsi_sum / total_tests if total_tests > 0 else 0

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

            .metric-card {{ 
                background: #ffffff; 
                border: 1px solid #e2e8f0; 
                border-radius: 12px; 
                padding: 24px; 
                text-align: center; 
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05); 
            }}
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

            .scrollable-text {{ 
                display: block; 
                width: 100%; 
                overflow-x: auto; 
                white-space: nowrap; 
                padding-bottom: 4px; 
                scrollbar-width: none; 
            }}
            .scrollable-text::-webkit-scrollbar {{ display: none; }}
            .scrollable-text:hover::-webkit-scrollbar {{ display: block; height: 6px; }}
            .scrollable-text::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 3px; }}

            .badge {{ display: inline-flex; align-items: center; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; line-height: 1.5; white-space: nowrap; box-shadow: inset 0 0 0 1px rgba(0,0,0,0.05); }}
            .badge-danger {{ background-color: var(--danger-bg); color: var(--danger-text); }}
            .badge-warning {{ background-color: var(--warning-bg); color: var(--warning-text); }}
            .badge-success {{ background-color: var(--success-bg); color: var(--success-text); }}
            .text-danger {{ color: var(--danger); }}
            .text-warning {{ color: var(--warning); }}
            .text-success {{ color: var(--success); }}
            .text-info {{ color: var(--info); }}
            .text-orange {{ color: var(--orange); }}
            .text-muted {{ color: var(--text-muted); }}

            .clickable-row {{ cursor: pointer; transition: background-color 0.2s; }}
            .clickable-row:hover {{ background-color: #f1f5f9; }}
            .expand-hint {{ font-size: 12px; color: var(--text-muted); font-weight: 600; transition: color 0.2s; }}
            .clickable-row:hover .expand-hint {{ color: var(--primary); }}

            .details-row {{ 
                background-color: #f8fafc; 
                box-shadow: inset 0 4px 8px -4px rgba(0, 0, 0, 0.05), inset 0 -4px 8px -4px rgba(0, 0, 0, 0.05); 
            }} 
            .test-details {{ padding: 32px 24px; }}

            .details-section {{ margin-bottom: 32px; }}
            .details-section:last-child {{ margin-bottom: 0; }}
            .details-title {{ font-size: 14px; font-weight: 700; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }}

            .accordion-header {{ cursor: pointer; user-select: none; transition: opacity 0.2s; display: flex; align-items: center; }}
            .accordion-header:hover {{ opacity: 0.7; }}
            .accordion-icon {{ display: inline-block; width: 20px; font-size: 12px; }}

            .details-list {{ list-style: none; padding: 0; margin: 16px 0 0 0; display: flex; flex-direction: column; gap: 16px; }}

            .probe-item {{ 
                background: #ffffff; 
                border: 1px solid #e2e8f0; 
                border-left: 4px solid #cbd5e1;
                border-radius: 8px; 
                padding: 20px; 
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px -2px rgba(0, 0, 0, 0.02); 
                display: flex;
                flex-direction: column;
                transition: all 0.2s ease; 
            }}
            .probe-item:hover {{
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.03);
            }}

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

            .btn-small {{ 
                display: inline-flex; 
                align-items: center; 
                background-color: #ffffff; 
                color: var(--text-main); 
                border: 1px solid #cbd5e1; 
                text-decoration: none; 
                padding: 6px 12px; 
                border-radius: 6px; 
                font-size: 12px; 
                font-weight: 600; 
                transition: all 0.2s ease-in-out; 
                cursor: pointer; 
                box-shadow: 0 1px 2px rgba(0,0,0,0.02); 
                white-space: nowrap; 
            }}
            .btn-small:hover {{ background-color: #f1f5f9; border-color: #94a3b8; color: var(--primary); text-decoration: none; }}

            .triage-actions {{ 
                margin: 20px -20px -20px -20px; 
                padding: 14px 20px; 
                background-color: #f8fafc; 
                border-top: 1px solid #e2e8f0; 
                border-radius: 0 0 8px 8px;
                display: flex; 
                gap: 8px; 
                flex-wrap: wrap; 
                align-items: center;
            }}
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
            window.initialT1Count = {total_t1_unreviewed};
            window.initialT2Count = {total_t2_unreviewed};
            window.totalTestCount = {total_tests};

            function switchTab(tabId) {{
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.metrics-container').forEach(m => m.classList.remove('active'));

                document.getElementById(tabId).classList.add('active');
                if (window.event && window.event.currentTarget) {{
                    window.event.currentTarget.classList.add('active');
                }}

                if (tabId === 'probe-view') {{
                    document.getElementById('metrics-probe').classList.add('active');
                }} else {{
                    document.getElementById('metrics-test').classList.add('active');
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

            function triage(testId, probeId, decisionType, tagText) {{
                const probeEl = document.getElementById(`probe-${{testId}}-${{probeId}}`);
                const actionsContainer = document.getElementById(`actions-${{testId}}-${{probeId}}`);

                let tagClass = decisionType === 'action' ? 'tag-action' : 'tag-noise';
                actionsContainer.innerHTML = `<span class="triage-tag ${{tagClass}}">[ ${{tagText}} ]</span>`;

                probeEl.setAttribute('data-state', decisionType);

                if (decisionType === 'action') {{
                    probeEl.classList.add('action-required');

                    // SMART CASCADING: Globally flag this exact bug across ALL tests
                    const otherProbes = document.querySelectorAll(`li[data-probe-id="${{probeId}}"][data-state="unreviewed"]`);
                    otherProbes.forEach(otherProbeEl => {{
                        if (otherProbeEl.id !== probeEl.id) {{
                            const otherTestId = otherProbeEl.getAttribute('data-test-id');
                            const otherActionsContainer = document.getElementById(`actions-${{otherTestId}}-${{probeId}}`);

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
                    }});

                }} else if (decisionType === 'noise') {{
                    probeEl.classList.add('noise-item');
                    const noiseList = document.getElementById(`list-noise-${{testId}}`);
                    const noiseContainer = document.getElementById(`noise-section-${{testId}}`);
                    if(noiseContainer) noiseContainer.style.display = 'block';
                    if(noiseList) noiseList.appendChild(probeEl);
                }}

                updateBadge(testId);
                updateAccordionCounts(testId);
            }}

            function updateAccordionCounts(testId) {{
                const listT1 = document.getElementById(`list-t1-${{testId}}`);
                if (listT1) {{
                    const count = listT1.querySelectorAll('li:not([data-state="noise"]):not([data-state="action"])').length;
                    const header = document.getElementById(`count-t1-${{testId}}`);
                    if (header) header.innerText = `[${{count}} Probes]`;
                }}

                const listT2 = document.getElementById(`list-t2-${{testId}}`);
                if (listT2) {{
                    const count = listT2.querySelectorAll('li:not([data-state="noise"]):not([data-state="action"])').length;
                    const header = document.getElementById(`count-t2-${{testId}}`);
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
                const t1Unreviewed = document.querySelectorAll('li[data-tier="1"][data-state="unreviewed"]').length;
                const t2Unreviewed = document.querySelectorAll('li[data-tier="2"][data-state="unreviewed"]').length;
                const confirmedBugs = document.querySelectorAll('.tag-action, .tag-cascaded').length;
                const fullyTriaged = document.querySelectorAll('.status-pill.clear, .status-pill.action').length;

                document.getElementById('ui-t1-inbox').innerText = t1Unreviewed + ' / ' + window.initialT1Count;
                document.getElementById('ui-t2-inbox').innerText = t2Unreviewed + ' / ' + window.initialT2Count;
                document.getElementById('ui-oracles').innerText = confirmedBugs;
                document.getElementById('ui-triaged-tests').innerText = fullyTriaged + ' / ' + window.totalTestCount;
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
                    <div class="metric-value" id="ui-t2-inbox">{total_t2_unreviewed} / {total_t2_unreviewed}</div>
                    <div class="metric-label">Execution Crashes (Robustness Audit)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-oracles">0</div>
                    <div class="metric-label">Confirmed Vulnerabilities</div>
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

            <div class="tabs">
                <div class="tab active" onclick="switchTab('test-view')">Test Quality (Test-Centric)</div>
                <div class="tab" onclick="switchTab('probe-view')">Code Health (Probe-Centric)</div>
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
                    <h2>Probe Vulnerability List</h2>
                    <p>Shows how the system responded to each Perturbation point.</p>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th style="width: 100px;">Probe ID</th>
                                <th>Description</th>
                                <th style="width: 180px;">Resolution Tier</th>
                                <th class="text-right" style="width: 160px;">Test Catch Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            {probe_rows}
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
                        <h3>Test Class <span id="modalTestTitle" class="pane-subtitle"></span></h3>
                        <div id="modalTestCode" class="code-container"></div>
                    </div>
                    <div class="split-pane" id="modalTargetPane">
                        <h3>Target Class <span id="modalTargetTitle" class="pane-subtitle"></span></h3>
                        <div id="modalTargetCode" class="code-container"></div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/java.min.js"></script>
        <script>
            const fileCache = {file_cache_json};

            function openCodeModal(testClass, testMethod, targetClass, targetMethod) {{
                document.getElementById('modalTestTitle').innerText = '— ' + testClass + '.' + testMethod + '()';

                const targetPane = document.getElementById('modalTargetPane');
                if (targetClass) {{
                    targetPane.style.display = 'flex';
                    document.getElementById('modalTargetTitle').innerText = '— ' + targetClass + '.' + targetMethod + '()';
                    renderAndHighlight('modalTargetCode', fileCache[targetClass], targetMethod);
                }} else {{
                    targetPane.style.display = 'none';
                }}

                renderAndHighlight('modalTestCode', fileCache[testClass], testMethod);

                document.getElementById('codeModal').style.display = "block";
                document.body.style.overflow = "hidden";
            }}

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

                if (methodName && methodName !== 'unknown') {{
                    const codeEl = container.querySelector('code');
                    const regex = new RegExp("(\\\\b" + methodName + "\\\\b)", "g");
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

    dashboard_probes = []
    dashboard_tests = defaultdict(lambda: {'hit': 0, 'caught': 0, 'probes': []})

    global_tier3_probes = {}

    for pid, probe_desc in sorted(probes.items()):
        print(f"\nProbe {pid}: {probe_desc}")
        tests = hits.get(pid)

        if not tests:
            print("  SKIP: No tests hit this probe")
            skipped_count += 1
            continue

        test_results_dict, p_count, f_count, is_timeout, actions_map = evaluate(pid, tests, project_dir, agent_jar,
                                                                                target_package, dynamic_timeout)

        for t in tests:
            dashboard_tests[t]['hit'] += 1

        tier_assigned = "Unknown"

        if is_timeout:
            timeouts_count += 1
            tier2_error += 1
            global_tests_failed += len(tests)
            tier_assigned = "Tier 2 (Timeout)"
            for t in tests:
                dashboard_tests[t]['caught'] += 1
                dashboard_tests[t]['probes'].append({
                    'id': pid, 'desc': probe_desc, 'status': 'FAIL (TIMEOUT)', 'tier': 2,
                    'actions': ['Infinite Loop / Timeout']
                })

            dashboard_probes.append(
                {'id': pid, 'desc': probe_desc, 'tier': tier_assigned, 'catch_rate': "100% (Timeout)"})
            continue

        if test_results_dict:
            global_tests_passed += p_count
            global_tests_failed += f_count

            has_assert = False
            has_exception = False
            has_pass = False

            for t_name, status in test_results_dict.items():
                s_up = status.upper()
                t_tier = 1

                if "FAIL" in s_up:
                    dashboard_tests[t_name]['caught'] += 1
                    if "ASSERT" in s_up or "COMPARISON" in s_up or "MULTIPLEFAILURES" in s_up:
                        has_assert = True
                        t_tier = 3
                        if pid not in global_tier3_probes:
                            global_tier3_probes[pid] = t_name
                    else:
                        has_exception = True
                        t_tier = 2
                elif "PASS" in s_up:
                    has_pass = True

                t_actions = actions_map.get(t_name, [])
                dashboard_tests[t_name]['probes'].append({
                    'id': pid, 'desc': probe_desc, 'status': status, 'tier': t_tier, 'actions': t_actions
                })

            if has_assert:
                tier3_assert += 1
                tier_assigned = "Tier 3 (Assert)"
            elif has_exception:
                tier2_error += 1
                tier_assigned = "Tier 2 (Exception)"
            elif has_pass:
                tier1_survived += 1
                tier_assigned = "Tier 1 (Survived)"
            else:
                unknown_errors += 1

            dashboard_probes.append(
                {'id': pid, 'desc': probe_desc, 'tier': tier_assigned, 'catch_rate': f"{f_count}/{p_count + f_count}"})
        else:
            errors_count += 1

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

    html_file = generate_dashboard(project_dir, dashboard_probes, dashboard_tests, metrics, global_tier3_probes)
    print(f"\nDashboard generated at: {html_file}")

    webbrowser.open('file://' + os.path.realpath(html_file))


if __name__ == "__main__":
    main()
import json
import os
import re
import html as _html

try:
    from java_source import to_idea_link, build_file_cache
    from probe_analyser import parse_probe, get_warning
except ModuleNotFoundError:
    from .java_source import to_idea_link, build_file_cache
    from .probe_analyser import parse_probe, get_warning

OUT_DIR = "target/perturb"


# ---------------------------------------------------------------------------
# HTML / JS escaping utilities
# ---------------------------------------------------------------------------

def escape_html(text):
    return _html.escape(str(text))


def escape_js(text):
    if not text:
        return ""
    return str(text).replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')


def sanitize_id(text):
    return re.sub(r'\W+', '_', text)


# ---------------------------------------------------------------------------
# Shared HTML fragment builders
# ---------------------------------------------------------------------------

def build_action_trace(p):
    """Render the execution-trace block for a single probe entry."""
    action_list = p.get('actions', [])
    if not action_list:
        action_list = ["State modification applied"]

    exceptions = p.get('exceptions', [])
    exc_str = (
        f" <span class='trace-exception'>({escape_html(' | '.join(exceptions))})</span>"
        if exceptions else ""
    )

    disp = f"<span class='text-muted'>Execution Trace (Hit {len(action_list)} times):</span><br>"
    disp += "<div class='execution-trace'>"
    for idx, act in enumerate(action_list, 1):
        safe_act = escape_html(act)
        if idx == len(action_list):
            safe_act += exc_str
        disp += f"{idx}. {safe_act}<br>"
    disp += "</div>"
    return disp


# ---------------------------------------------------------------------------
# Probe-Centric (Ledger) tab builders
# ---------------------------------------------------------------------------

def build_ledger_row(p, project_dir, probe_status=None):
    class_name = p['fqcn'].split('.')[-1] if p['fqcn'] != 'unknown' else 'Unknown'
    hit_count = len(p['tests'])
    ps = probe_status or (
        'Survived' if p.get('tier') == 1 else
        'Clean Kill' if p.get('tier') == 3 else 'Unknown'
    )

    if ps == 'Un-hit':
        badge_class = ""
        badge_style = "background:#f1f5f9; color:var(--text-muted); border:1px solid var(--border-strong);"
        status_text = "Un-hit / Dead Code"
        row_style = "opacity:0.5;"
    elif ps == 'TIMEOUT':
        badge_class = "badge-warning"
        badge_style = ""
        status_text = "⏱ TIMEOUT"
        row_style = ""
    elif ps == 'Survived':
        badge_class = "badge-danger"
        badge_style = ""
        status_text = "Unprotected"
        row_style = ""
    elif ps == 'Clean Kill':
        badge_class = "badge-success"
        badge_style = ""
        status_text = "Clean Kill"
        row_style = ""
    elif ps == 'Dirty Kill':
        badge_class = "badge-warning"
        badge_style = ""
        status_text = "Dirty Kill"
        row_style = "opacity:0.75;"
    else:
        badge_class = ""
        badge_style = "background:#f1f5f9; color:var(--text-muted); border:1px solid var(--border-strong);"
        status_text = ps
        row_style = ""

    witness_list = (
        "".join([f"<li style='margin-bottom: 4px;'>{escape_html(t)}</li>" for t in p['tests']])
        if p['tests'] else
        "<li style='color:var(--text-muted); font-style:italic;'>No tests hit this probe.</li>"
    )
    ide_link = to_idea_link(project_dir, p['fqcn'], False)

    return f"""
    <tr id='ledger-row-{p['id']}' class="clickable-row" style="{row_style}" onclick="toggleRow(event, 'ledger-desc-{p['id']}')">
        <td><div class="scrollable-text font-medium code-font">#{p['id']}</div></td>
        <td><div class="scrollable-text code-font">{class_name}.{p['method']}()</div></td>
        <td><div class="scrollable-text">{escape_html(p['desc'])}</div></td>
        <td class="text-center"><div class="scrollable-text" style="text-align:center;">{hit_count} Test{'s' if hit_count != 1 else ''}</div></td>
        <td class="text-right"><div class="scrollable-text" style="text-align:right;"><span id="ledger-badge-{p['id']}" class="badge {badge_class}" style="{badge_style}">{status_text}</span></div></td>
    </tr>
    <tr id="ledger-desc-{p['id']}" class="details-row" style="display: none;">
        <td colspan="5" class="p-0">
            <div class="test-details">
                <div style="display: flex; gap: 24px; margin-bottom: 0;">
                    <div style="flex: 2; overflow: hidden; min-width: 0;">
                        <h4 style="margin: 0 0 10px 0; font-size: 11px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.06em; font-weight: 700; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">Witness List</h4>
                        <ul style="max-height: 150px; overflow-y: auto; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; padding-left: 18px; color: var(--text-main); margin: 0;">
                            {witness_list}
                        </ul>
                    </div>
                    <div style="flex: 1; display: flex; flex-direction: column; justify-content: flex-start; gap: 8px; border-left: 1px solid var(--border-color); padding-left: 24px; min-width: 200px;">
                        <h4 style="margin: 0 0 2px 0; font-size: 11px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.06em; font-weight: 700; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">Actions</h4>
                        <a href="{ide_link}" class="btn-small" style="text-align: center; width: 100%;">Open in IDE</a>
                        <button class="btn-small" style="width: 100%;" onclick="event.stopPropagation(); openCodeModal('{escape_js(p['fqcn'])}', '{escape_js(p['method'])}', null, null)">View Source</button>
                        <div class='ledger-resolve-wrap'>
                            <button class='btn-resolve' data-resolve-ledger="{p['id']}"
                                onclick="event.stopPropagation(); markResolved('{p['id']}', 'ledger', this)">
                                Mark as Fixed
                            </button>
                            <div style='font-size:11px; color:var(--success-text); margin-top:6px;'>I have written a new test covering this probe.</div>
                        </div>
                    </div>
                </div>
            </div>
        </td>
    </tr>
    """


def build_ledger_table(rows_html, tbody_id):
    return f"""
    <div class="table-container" style="margin-top: 14px;">
        <table>
            <thead>
                <tr>
                    <th style="width: 110px;">Probe ID</th>
                    <th style="width: 300px;">Target</th>
                    <th>Perturbation</th>
                    <th class="text-center" style="width: 150px;">Hit by Tests</th>
                    <th class="text-right" style="width: 210px;">Status</th>
                </tr>
            </thead>
            <tbody id="{tbody_id}">
                {rows_html}
            </tbody>
        </table>
    </div>
    """


def build_ledger_html(master_probes, project_dir):
    """Build the full Probe-Centric tab HTML."""

    def mp_to_ledger_p(mp):
        return {
            'id': mp['id'], 'desc': mp['desc'], 'fqcn': mp['fqcn'],
            'method': mp['method'], 'tests': sorted(mp['test_outcomes'].keys()),
        }

    ledger_t1 = []
    ledger_t3 = []
    ledger_dirty = []
    ledger_timeout = []
    ledger_unhit = []

    for pid, mp in sorted(master_probes.items(), key=lambda x: -len(x[1]['test_outcomes'])):
        lp = mp_to_ledger_p(mp)
        if mp['status'] == 'Survived':
            ledger_t1.append(lp)
        elif mp['status'] == 'Clean Kill':
            ledger_t3.append(lp)
        elif mp['status'] == 'Dirty Kill':
            ledger_dirty.append(lp)
        elif mp['status'] == 'TIMEOUT':
            ledger_timeout.append(lp)
        elif mp['status'] == 'Un-hit':
            ledger_unhit.append(lp)

    ledger_html = ""

    if ledger_t1:
        rows_html = "".join([build_ledger_row(p, project_dir, 'Survived') for p in ledger_t1])
        ledger_html += f"""
        <div class='details-section'>
            <div class='details-title text-danger accordion-header' onclick="toggleAccordion('content-ledger-t1', 'icon-ledger-t1')">
                <span><span id='icon-ledger-t1' class='accordion-icon'>▼</span> Unprotected (Survived) <span id='count-ledger-t1'>[{len(ledger_t1)} Probes]</span></span>
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
        rows_html = "".join([build_ledger_row(p, project_dir, 'Clean Kill') for p in ledger_t3])
        ledger_html += f"""
        <div class='details-section'>
            <div class='details-title text-success accordion-header' onclick="toggleAccordion('content-ledger-t3', 'icon-ledger-t3')">
                <span><span id='icon-ledger-t3' class='accordion-icon'>▶</span> Clean Kills (Assert) <span id='count-ledger-t3'>[{len(ledger_t3)} Probes]</span></span>
            </div>
            <div id='content-ledger-t3' style='display: none;'>
                {build_ledger_table(rows_html, 'tbody-ledger-t3')}
            </div>
        </div>
        """

    if ledger_dirty or ledger_timeout:
        all_dirty = ledger_dirty + ledger_timeout
        rows_html = "".join([
            build_ledger_row(p, project_dir, 'Dirty Kill' if p in ledger_dirty else 'TIMEOUT')
            for p in all_dirty
        ])
        ledger_html += f"""
        <div class='details-section'>
            <div class='details-title text-warning accordion-header' onclick="toggleAccordion('content-ledger-dirty', 'icon-ledger-dirty')">
                <span><span id='icon-ledger-dirty' class='accordion-icon'>▶</span> Dirty Kills / Timeouts <span id='count-ledger-dirty'>[{len(all_dirty)} Probes]</span></span>
            </div>
            <div id='content-ledger-dirty' style='display: none;'>
                {build_ledger_table(rows_html, 'tbody-ledger-dirty')}
            </div>
        </div>
        """

    if ledger_unhit:
        rows_html = "".join([build_ledger_row(p, project_dir, 'Un-hit') for p in ledger_unhit])
        ledger_html += f"""
        <div class='details-section'>
            <div class='details-title text-muted accordion-header' onclick="toggleAccordion('content-ledger-unhit', 'icon-ledger-unhit')">
                <span><span id='icon-ledger-unhit' class='accordion-icon'>▶</span> Un-hit / Dead Code <span id='count-ledger-unhit'>[{len(ledger_unhit)} Probes]</span></span>
            </div>
            <div id='content-ledger-unhit' style='display: none;'>
                {build_ledger_table(rows_html, 'tbody-ledger-unhit')}
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

    return ledger_html


# ---------------------------------------------------------------------------
# Test-Centric tab builder
# ---------------------------------------------------------------------------

def build_test_rows(test_stats, test_summary, global_tier3_probes, project_dir):
    """Build all test row HTML for the Test-Centric tab.

    Returns (test_rows_html, total_tests, total_t1_unreviewed, fully_triaged_tests).
    """

    def test_sort_key(item):
        t_name = item[0]
        s = test_summary.get(t_name, {'clean': 0, 'dirty': 0, 'survived': 0})
        return (-s['survived'], -(s['clean'] + s['dirty'] + s['survived']))

    valid_sorted_tests = []
    for test_name, stats in sorted(test_stats.items(), key=lambda x: x[0]):
        t1 = []
        t2_exceptions = []
        t3 = []
        t_covered = []

        for p in stats['probes']:
            if p['tier'] == 3:
                t3.append(p)
            elif p['tier'] == 2:
                t2_exceptions.append(p)
            elif p['id'] in global_tier3_probes:
                p['saviour'] = global_tier3_probes[p['id']]
                t_covered.append(p)
            elif p['tier'] == 1:
                t1.append(p)

        total_footprint = len(t1) + len(t2_exceptions) + len(t3) + len(t_covered)
        if total_footprint == 0:
            continue

        valid_sorted_tests.append((test_name, stats, t1, t2_exceptions, t3, t_covered, total_footprint))

    valid_sorted_tests.sort(key=test_sort_key)

    total_tests = len(valid_sorted_tests)
    total_t1_unreviewed = 0
    fully_triaged_tests = 0
    test_rows = ""

    for test_name, stats, t1, t2_exceptions, t3, t_covered, total_footprint in valid_sorted_tests:
        safe_id = sanitize_id(test_name)
        unreviewed_count = len(t1)
        total_t1_unreviewed += unreviewed_count

        ts = test_summary.get(test_name, {'clean': 0, 'dirty': 0, 'survived': 0})
        n_clean    = ts['clean']
        n_dirty    = ts['dirty']
        n_survived = ts['survived']
        is_vulnerable = n_survived > 0

        if unreviewed_count == 0:
            status_pill = '<span class="status-pill clear">[ Fully Triaged ]</span>'
            fully_triaged_tests += 1
        else:
            status_pill = f'<span class="status-pill {"action" if is_vulnerable else "pending"}">[ {unreviewed_count} Unreviewed ]</span>'

        _dot = "display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;font-size:11px;font-weight:700;flex-shrink:0;"
        footprint_badges = ""
        if n_clean:
            footprint_badges += f'<span style="{_dot}background:var(--success-bg);color:var(--success-text);border:1px solid #a7f3d0;" title="Clean kills (assertion failures)">{n_clean}</span>'
        if n_dirty:
            footprint_badges += f'<span style="{_dot}background:var(--warning-bg);color:var(--warning-text);border:1px solid #fde68a;" title="Exception crashes">{n_dirty}</span>'
        if n_survived:
            footprint_badges += f'<span style="{_dot}background:var(--danger-bg);color:var(--danger-text);border:1px solid #fecaca;" title="Survived (missed by this test)">{n_survived}</span>'
        if not footprint_badges:
            footprint_badges = f'<span style="{_dot}background:#f1f5f9;color:var(--text-muted);border:1px solid var(--border-strong);" title="Total probes">{total_footprint}</span>'

        badge_html = status_pill

        test_class = test_name.split('#')[0]
        test_method = test_name.split('#')[1] if '#' in test_name else "unknown"
        test_link = to_idea_link(project_dir, test_class, is_test=True)

        display_test_class = test_class.split('.')[-1]
        display_test_name = f"{display_test_class}.{test_method}()" if test_method != "unknown" else display_test_class

        inner_html = f"<div class='test-details'>"

        if t1:
            inner_html += f"""
            <div style='margin-bottom: 16px; padding: 10px 14px; background: #f8fafc; border: 1px solid var(--border-color); border-radius: var(--radius-md); display: flex; align-items: center; gap: 12px; justify-content: space-between;'>
                <span style='font-size: 12px; color: var(--text-muted);'>
                    <strong style='color: var(--text-main);'>Utilities</strong> &mdash; Heuristic tools to reduce triage fatigue.
                </span>
                <button class='btn-small' style='border-style: dashed; color: var(--text-muted); flex-shrink: 0;'
                    title='Group all unreviewed probes by target class and bulk-triage them as Out of Scope.'
                    onclick="event.stopPropagation(); openBulkTriageModal('{safe_id}', '{escape_js(test_class)}')">
                    🧹 Bulk Triage (By Target)
                </button>
            </div>
            """

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
                        <li id='probe-{safe_id}-{p['id']}' data-probe-id='{p['id']}' data-test-id='{safe_id}' data-tier='1' data-state='unreviewed' data-target-fqcn='{escape_js(fqcn)}' class='probe-item' style='border-left-color: var(--danger);'>
                            <div class='probe-meta'>
                                <span class='probe-id'>Probe {p['id']}</span>
                                <div class='action-group'>
                                    <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(test_class)}', '{escape_js(test_method)}', '{escape_js(fqcn)}', '{escape_js(m_name)}')">View Source</button>
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
                            <div id='resolve-wrap-{safe_id}-{p['id']}' style='display:none; margin: 12px -20px -18px -20px; padding: 10px 20px; background: var(--success-bg); border-top: 1px solid #a7f3d0; border-radius: 0 0 var(--radius-md) var(--radius-md);'>
                                <button class='btn-resolve' data-resolve-test="{p['id']}-{safe_id}"
                                    onclick="event.stopPropagation(); markResolved('{p['id']}', 'test-{safe_id}', this)">
                                    Mark as Fixed
                                </button>
                                <span style='font-size:11px; color:var(--success-text); margin-left:10px;'>I have written / improved the test for this probe.</span>
                            </div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        if t2_exceptions:
            inner_html += f"""
            <div class='details-section'>
                <div class='details-title text-warning accordion-header' onclick="toggleAccordion('content-t2-{safe_id}', 'icon-t2-{safe_id}')">
                    <span><span id='icon-t2-{safe_id}' class='accordion-icon'>▶</span> Exception Crashes (Dirty Kills) <span id='count-t2-{safe_id}'>[{len(t2_exceptions)} Probes]</span></span>
                </div>
                <div id='content-t2-{safe_id}' style='display: none;'>
                    <ul class='details-list'>
            """
            for p in t2_exceptions:
                mod, fqcn, m_name = parse_probe(p['desc'])
                target_link = to_idea_link(project_dir, fqcn, is_test=False)
                action_disp = build_action_trace(p)
                inner_html += f"""
                        <li class='probe-item' style='border-left-color: var(--warning); opacity:0.8;'>
                            <div class='probe-meta'>
                                <span class='probe-id'>Probe {p['id']}</span>
                                <div class='action-group'>
                                    <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(test_class)}', '{escape_js(test_method)}', '{escape_js(fqcn)}', '{escape_js(m_name)}')">View Source</button>
                                    <a href="{target_link}" class="btn-small">Open Target</a>
                                    <a href="{test_link}" class="btn-small">Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                            <div style='margin-top:8px; font-size:12px; color:var(--warning-text); background:var(--warning-bg); padding:7px 12px; border-radius:var(--radius-sm); border:1px solid #fde68a;'>
                                Exception-level crash &mdash; reviewed in <strong>Code-Centric</strong> tab.
                            </div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

        inner_html += f"""
        <div class='details-section' id='cascaded-section-{safe_id}' style='display: none;'>
            <div class='details-title text-orange accordion-header' onclick="toggleAccordion('content-cascaded-{safe_id}', 'icon-cascaded-{safe_id}')">
                <span><span id='icon-cascaded-{safe_id}' class='accordion-icon'>▶</span> Also Needs Fixing (Seen Elsewhere) <span id='count-cascaded-{safe_id}'>[0 Probes]</span></span>
            </div>
            <div id='content-cascaded-{safe_id}' style='display: none;'>
                <ul id='list-cascaded-{safe_id}' class='details-list'></ul>
            </div>
        </div>
        """

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
                        <li class='probe-item' style='border-left-color: var(--info);'>
                            <div class='probe-meta'>
                                <span class='probe-id'>Probe {p['id']}</span>
                                <div class='action-group'>
                                    <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(test_class)}', '{escape_js(test_method)}', '{escape_js(fqcn)}', '{escape_js(m_name)}')">View Source</button>
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
                                    <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(test_class)}', '{escape_js(test_method)}', '{escape_js(fqcn)}', '{escape_js(m_name)}')">View Source</button>
                                    <a href="{target_link}" class="btn-small">Open Target</a>
                                    <a href="{test_link}" class="btn-small">Open Test</a>
                                </div>
                            </div>
                            <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                            <div class='perturb-action'>{action_disp}</div>
                        </li>
                        """
            inner_html += "</ul></div></div>"

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
            <td class="text-center"><div class="scrollable-text" style="text-align:center; display:flex; gap:4px; justify-content:center; align-items:center;">{footprint_badges}</div></td>
            <td id="badge-{safe_id}" class="text-right"><div class="scrollable-text" style="text-align:right;">{badge_html}</div></td>
        </tr>
        <tr id="desc-{safe_id}" class="details-row" style="display: none;">
            <td colspan="3" class="p-0">{inner_html}</td>
        </tr>
        """

    return test_rows, total_tests, total_t1_unreviewed, fully_triaged_tests


# ---------------------------------------------------------------------------
# Code-Centric tab builder
# ---------------------------------------------------------------------------

def build_code_rows(dashboard_methods, master_probes, project_dir):
    """Build all method row HTML for the Code-Centric tab.

    Returns (code_rows_html, valid_methods_count, total_t2_unreviewed).
    """
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
            action_disp = build_action_trace(p)
            ide_link = to_idea_link(project_dir, m_fqcn, False)

            mp_data = master_probes.get(p['id'])
            test_items = ""
            n_clean = n_dirty = n_survived = 0
            if mp_data:
                for t_name, outcome in mp_data['test_outcomes'].items():
                    if outcome == 'clean':
                        color = 'var(--success-text)'; bg = 'var(--success-bg)'; label = 'Clean Kill'
                        n_clean += 1
                    elif outcome == 'dirty':
                        color = 'var(--warning-text)'; bg = 'var(--warning-bg)'; label = 'Exception'
                        n_dirty += 1
                    elif outcome == 'timeout':
                        color = 'var(--warning-text)'; bg = 'var(--warning-bg)'; label = 'TIMEOUT'
                        n_dirty += 1
                    else:
                        color = 'var(--danger-text)'; bg = 'var(--danger-bg)'; label = 'Survived'
                        n_survived += 1
                    test_items += f"<li style='margin-bottom:3px; display:flex; align-items:center; gap:8px;'><span style='font-size:11px; font-weight:600; color:{color}; background:{bg}; padding:2px 7px; border-radius:9999px; flex-shrink:0;'>{label}</span><span class='code-font' style='font-size:12px; color:var(--text-muted);'>{escape_html(t_name)}</span></li>"
            if not test_items:
                test_items = "<li style='color:var(--text-muted); font-style:italic;'>No outcomes recorded.</li>"
            total_witnesses = n_clean + n_dirty + n_survived
            summary = f"Hit by {total_witnesses} test{'s' if total_witnesses!=1 else ''}. <strong style='color:var(--success-text);'>{n_clean} clean</strong>, <strong style='color:var(--warning-text);'>{n_dirty} crashed</strong>, <strong style='color:var(--danger-text);'>{n_survived} missed</strong>."

            inner_code_html += f"""
            <li id='code-probe-{p['id']}' data-state='unreviewed' class='probe-item' style='border-left-color: var(--warning);'>
                <div class='probe-meta'>
                    <span class='probe-id'>Probe {p['id']}</span>
                    <div class='action-group'>
                        <button class="btn-small" onclick="event.stopPropagation(); openCodeModal('{escape_js(m_fqcn)}', '{escape_js(m_name)}', null, null)">View Source</button>
                        <a href="{ide_link}" class="btn-small">Open in IDE</a>
                    </div>
                </div>
                <div class='probe-desc scrollable-text'>{escape_html(p['desc'])}</div>
                <div class='perturb-action'>{action_disp}</div>
                <div style='margin-top: 10px; font-size: 13px; color: var(--text-muted); background: #f8fafc; padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-color);'>
                    <p style='margin:0 0 8px 0;'>{summary}</p>
                    <ul style='margin:0; padding-left:0; list-style:none; max-height:120px; overflow-y:auto;'>{test_items}</ul>
                </div>
                <div class='triage-actions' id='code-actions-{p['id']}'>
                    <button class='btn-triage btn-action' title='The code lacks defensive checks. I will add defensive checks to the production code.' onclick="triageCode('{safe_m_id}', '{p['id']}', 'action-code', 'Brittle Code')">Brittle Code</button>
                    <button class='btn-triage btn-noise' title='This state can mathematically never happen in the real app.' onclick="triageCode('{safe_m_id}', '{p['id']}', 'equivalent-code', 'Impossible State')">Impossible State</button>
                </div>
                <div id='code-resolve-wrap-{p['id']}' style='display:none; margin: 12px -20px -18px -20px; padding: 10px 20px; background: var(--success-bg); border-top: 1px solid #a7f3d0; border-radius: 0 0 var(--radius-md) var(--radius-md);'>
                    <button class='btn-resolve' data-resolve-code="{p['id']}"
                        onclick="event.stopPropagation(); markResolved('{p['id']}', 'code', this)">
                        Mark as Fixed
                    </button>
                    <span style='font-size:11px; color:var(--success-text); margin-left:10px;'>I have fixed the brittle code for this probe.</span>
                </div>
            </li>
            """
        inner_code_html += "</ul></div></div>"

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
            <td class="text-center"><div class="scrollable-text font-medium text-warning" style="text-align:center;">{len(stats['probes'])} Crashes</div></td>
            <td id="code-badge-{safe_m_id}" class="text-right"><div class="scrollable-text" style="text-align:right;">
                <span class="status-pill pending">[ {len(stats['probes'])} Unreviewed ]</span>
            </div></td>
        </tr>
        <tr id="code-desc-{safe_m_id}" class="details-row" style="display: none;">
            <td colspan="3" class="p-0">
                <div class="test-details" style="padding-top: 16px;">{inner_code_html}</div>
            </td>
        </tr>
        """

    return code_rows, valid_methods_count, total_t2_unreviewed


# ---------------------------------------------------------------------------
# Top-level dashboard generator
# ---------------------------------------------------------------------------

def generate_dashboard(project_dir, dashboard_ledger, dashboard_methods, test_stats,
                       test_summary, metrics, global_tier3_probes, master_probes):
    """
    Generate the full HTML dashboard and write it to disk.

    Returns the path to the written HTML file.
    """
    html_path = os.path.join(project_dir, OUT_DIR, "dashboard.html")

    all_probe_ids = sorted(master_probes.keys())
    probe_ids_json = json.dumps(all_probe_ids)

    file_cache = build_file_cache(project_dir, test_stats, dashboard_ledger, dashboard_methods)
    file_cache_json = json.dumps(file_cache).replace("</", "<\\/")

    ledger_html = build_ledger_html(master_probes, project_dir)

    test_rows, total_tests, total_t1_unreviewed, fully_triaged_tests = build_test_rows(
        test_stats, test_summary, global_tier3_probes, project_dir,
    )

    code_rows, valid_methods_count, total_t2_unreviewed = build_code_rows(
        dashboard_methods, master_probes, project_dir,
    )

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
                --bg-main: #f1f5f9;
                --bg-card: #ffffff;
                --text-main: #0f172a;
                --text-muted: #64748b;
                --border-color: #e2e8f0;
                --border-strong: #cbd5e1;
                --danger: #dc2626;
                --danger-bg: #fef2f2;
                --danger-text: #991b1b;
                --warning: #d97706;
                --warning-bg: #fffbeb;
                --warning-text: #92400e;
                --success: #059669;
                --success-bg: #ecfdf5;
                --success-text: #065f46;
                --info: #0284c7;
                --info-bg: #f0f9ff;
                --info-text: #0369a1;
                --orange: #ea580c;
                --orange-bg: #fff7ed;
                --primary: #2563eb;
                --primary-bg: #eff6ff;
                --radius-sm: 6px;
                --radius-md: 8px;
                --radius-lg: 12px;
                --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
                --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
            }}
            * {{ box-sizing: border-box; }}
            body {{
                font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                background-color: var(--bg-main);
                color: var(--text-main);
                margin: 0;
                padding: 32px 0 48px;
                line-height: 1.5;
                font-size: 15px;
            }}
            .container {{ width: 100%; padding: 0 40px; }}
            h1 {{ font-size: 22px; font-weight: 700; margin: 0; color: var(--text-main); letter-spacing: -0.02em; }}

            .metrics-container {{ display: none; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 28px; }}
            .metrics-container.active {{ display: grid; }}

            .metric-card {{ background: #ffffff; border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 20px 24px; text-align: left; box-shadow: var(--shadow-sm); }}
            .metric-value {{ font-size: 28px; font-weight: 700; color: var(--text-main); line-height: 1.1; margin-bottom: 4px; letter-spacing: -0.02em; }}
            .metric-label {{ font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }}

            .tabs {{ display: flex; border-bottom: 1px solid var(--border-color); margin-bottom: 24px; gap: 0; }}
            .tab {{ padding: 11px 20px; font-size: 14px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: all 0.15s ease; }}
            .tab:hover {{ color: var(--text-main); }}
            .tab.active {{ color: var(--primary); border-bottom-color: var(--primary); }}
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; }}

            .tab-header {{ margin-bottom: 20px; }}
            .tab-header h2 {{ font-size: 17px; font-weight: 700; margin: 0 0 4px 0; color: var(--text-main); letter-spacing: -0.01em; }}
            .tab-header p {{ margin: 0; color: var(--text-muted); font-size: 14px; }}

            .table-container {{ background: #ffffff; border: 1px solid var(--border-color); border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow-sm); }}
            table {{ width: 100%; table-layout: fixed; border-collapse: collapse; text-align: left; }}
            th, td {{ padding: 13px 20px; border-bottom: 1px solid var(--border-color); font-size: 14px; overflow: hidden; }}
            th {{ background-color: #f8fafc; font-weight: 600; color: #475569; text-transform: uppercase; font-size: 12px; letter-spacing: 0.06em; border-bottom: 1px solid var(--border-color); }}

            .text-center {{ text-align: center; }}
            .text-right {{ text-align: right; }}
            .font-medium {{ font-weight: 500; }}
            .code-font {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px; font-weight: 600; color: var(--text-main); }}
            .p-0 {{ padding: 0 !important; }}

            .scrollable-text {{ display: block; width: 100%; overflow-x: auto; white-space: nowrap; scrollbar-width: none; }}
            .scrollable-text::-webkit-scrollbar {{ display: none; }}

            .badge {{ display: inline-flex; align-items: center; padding: 4px 11px; border-radius: 9999px; font-size: 12px; font-weight: 600; line-height: 1.5; white-space: nowrap; }}
            .badge-danger {{ background-color: var(--danger-bg); color: var(--danger-text); border: 1px solid #fecaca; }}
            .badge-warning {{ background-color: var(--warning-bg); color: var(--warning-text); border: 1px solid #fde68a; }}
            .badge-success {{ background-color: var(--success-bg); color: var(--success-text); border: 1px solid #a7f3d0; }}
            .badge-primary {{ background-color: var(--primary-bg); color: #1e40af; border: 1px solid #bfdbfe; }}

            .text-danger {{ color: var(--danger) !important; border-bottom-color: var(--danger) !important; }}
            .text-warning {{ color: var(--warning) !important; border-bottom-color: var(--warning) !important; }}
            .text-success {{ color: var(--success) !important; border-bottom-color: var(--success) !important; }}
            .text-info {{ color: var(--info) !important; border-bottom-color: var(--info) !important; }}
            .text-orange {{ color: var(--orange) !important; border-bottom-color: var(--orange) !important; }}
            .text-muted {{ color: var(--text-muted) !important; border-bottom-color: var(--text-muted) !important; }}
            .text-primary {{ color: var(--primary) !important; border-bottom-color: var(--primary) !important; }}
            .text-main {{ color: var(--text-main); }}

            .clickable-row {{ cursor: pointer; transition: background-color 0.15s; }}
            .clickable-row:hover {{ background-color: #f8fafc; }}
            .expand-hint {{ font-size: 13px; color: var(--text-muted); font-weight: 600; letter-spacing: 0.02em; transition: color 0.15s; white-space: nowrap; }}
            .clickable-row:hover .expand-hint {{ color: var(--primary); }}

            .details-row {{ background-color: #f8fafc; }}
            .test-details {{ padding: 28px 24px; }}

            .details-section {{ margin-bottom: 28px; }}
            .details-section:last-child {{ margin-bottom: 0; }}
            .details-title {{ font-size: 13px; font-weight: 700; border-bottom: 2px solid; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 0.07em; }}

            .accordion-header {{ cursor: pointer; user-select: none; transition: opacity 0.15s; display: flex; align-items: center; }}
            .accordion-header:hover {{ opacity: 0.7; }}
            .accordion-icon {{ display: inline-block; width: 18px; font-size: 10px; }}

            .details-list {{ list-style: none; padding: 0; margin: 14px 0 0 0; display: flex; flex-direction: column; gap: 12px; }}

            .probe-item {{ background: #ffffff; border: 1px solid var(--border-color); border-left: 3px solid var(--border-strong); border-radius: var(--radius-md); padding: 18px 20px; display: flex; flex-direction: column; transition: box-shadow 0.15s ease; }}
            .probe-item:hover {{ box-shadow: var(--shadow-md); }}

            .probe-meta {{ display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }}
            .probe-id {{ font-weight: 700; color: var(--text-muted); font-size: 13px; letter-spacing: 0.03em; text-transform: uppercase; }}
            .probe-desc {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px; color: var(--text-main); margin-bottom: 10px; background: #f8fafc; padding: 9px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); }}
            .probe-warning {{ background-color: var(--danger-bg); color: var(--danger-text); padding: 10px 14px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; margin-top: 10px; border-left: 3px solid var(--danger); }}

            .perturb-action {{ font-size: 13px; margin-top: 4px; display: inline-block; color: var(--text-main); width: 100%; }}
            .execution-trace {{ max-height: 90px; overflow-y: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; margin-top: 6px; padding: 8px 12px; background: #f8fafc; border-left: 3px solid var(--border-strong); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }}

            .saviour-box {{ margin-top: 14px; font-size: 13px; padding: 10px 14px; background-color: var(--info-bg); border-radius: var(--radius-sm); border: 1px solid #bae6fd; border-left: 3px solid var(--info); }}
            .saviour-link {{ font-family: ui-monospace, SFMono-Regular, monospace; font-weight: 600; text-decoration: none; color: var(--primary); cursor: pointer; transition: color 0.15s; }}
            .saviour-link:hover {{ color: var(--text-main); text-decoration: underline; }}

            .action-group {{ display: flex; align-items: center; gap: 6px; margin-left: auto; flex-wrap: nowrap; }}

            .btn-small, .btn-primary, .btn-resolve, .btn-triage {{
                display: inline-flex; align-items: center; justify-content: center;
                height: 32px; padding: 0 13px;
                border-radius: var(--radius-sm); font-size: 13px; font-weight: 600;
                cursor: pointer; transition: all 0.15s ease; white-space: nowrap;
                text-decoration: none; line-height: 1;
            }}
            .btn-small {{ background: #ffffff; color: var(--text-main); border: 1px solid var(--border-strong); box-shadow: var(--shadow-sm); }}
            .btn-small:hover {{ background: #f1f5f9; border-color: #94a3b8; color: var(--primary); text-decoration: none; }}
            .btn-primary {{ background: var(--primary); color: #ffffff; border: none; box-shadow: 0 1px 3px rgba(37,99,235,0.3); height: 32px; padding: 0 14px; }}
            .btn-primary:hover {{ background: #1d4ed8; color: #ffffff; text-decoration: none; }}

            .triage-actions {{ margin: 16px -20px -18px -20px; padding: 12px 20px; background-color: #f8fafc; border-top: 1px solid var(--border-color); border-radius: 0 0 var(--radius-md) var(--radius-md); display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
            .btn-triage {{ height: 30px; padding: 0 13px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; font-weight: 600; transition: all 0.15s; border: 1px solid transparent; background: transparent; }}
            .btn-action {{ color: var(--danger); border-color: #fca5a5; background: #ffffff; }}
            .btn-action:hover {{ background: var(--danger-bg); border-color: var(--danger); }}
            .btn-noise {{ color: var(--text-muted); border-color: var(--border-strong); background: #ffffff; }}
            .btn-noise:hover {{ background: #f1f5f9; color: var(--text-main); border-color: #94a3b8; }}

            .cascaded-item {{ border-left-color: var(--orange) !important; }}
            .action-required {{ border-left-color: var(--danger) !important; }}
            .noise-item {{ opacity: 0.55; border-left-color: var(--border-strong) !important; }}

            .triage-tag {{ display: inline-block; padding: 4px 10px; border-radius: var(--radius-sm); font-weight: 600; font-size: 13px; }}
            .tag-action {{ background: var(--danger-bg); color: var(--danger-text); border: 1px solid #fecaca; }}
            .tag-cascaded {{ background: var(--orange-bg); color: var(--orange); border: 1px solid #fdba74; }}
            .tag-noise {{ background: #f1f5f9; color: var(--text-muted); border: 1px solid var(--border-strong); }}

            .status-pill {{ display: inline-block; padding: 5px 13px; border-radius: 9999px; font-size: 13px; font-weight: 600; white-space: nowrap; }}
            .status-pill.clear {{ background: var(--success-bg); color: var(--success-text); border: 1px solid #a7f3d0; }}
            .status-pill.action {{ background: var(--danger-bg); color: var(--danger-text); border: 1px solid #fecaca; }}
            .status-pill.mid {{ background: var(--warning-bg); color: var(--warning-text); border: 1px solid #fde68a; }}
            .status-pill.pending {{ background: #f1f5f9; color: var(--text-muted); border: 1px solid var(--border-strong); }}

            .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(15, 23, 42, 0.65); backdrop-filter: blur(3px); }}
            .modal-content {{ background-color: #ffffff; margin: 2% auto; padding: 24px; border: 1px solid var(--border-color); width: 94%; height: 85%; border-radius: var(--radius-lg); box-shadow: 0 20px 40px -8px rgba(0, 0, 0, 0.2); display: flex; flex-direction: column; }}
            .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color); }}
            .modal-header h2 {{ margin: 0; font-size: 16px; color: var(--text-main); font-weight: 700; }}
            .close {{ color: var(--text-muted); font-size: 24px; font-weight: bold; cursor: pointer; transition: color 0.15s; line-height: 1; }}
            .close:hover {{ color: var(--text-main); }}

            .split-view {{ display: flex; gap: 16px; height: 100%; overflow: hidden; }}
            .split-pane {{ flex: 1; display: flex; flex-direction: column; border: 1px solid var(--border-color); border-radius: var(--radius-md); overflow: hidden; background: #f8fafc; }}
            .split-pane h3 {{ margin: 0; padding: 12px 16px; background: #ffffff; border-bottom: 1px solid var(--border-color); font-size: 12px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 8px; }}
            .pane-subtitle {{ font-weight: 500; color: var(--primary); font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

            .code-container {{ flex: 1; overflow: auto; background: #ffffff; padding: 16px 20px; }}
            .code-container pre {{ margin: 0; }}
            .code-container code {{ font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace; font-size: 12px; line-height: 1.6; }}
            mark.scroll-target {{ background-color: #fef08a; color: #854d0e; border-radius: 3px; padding: 1px 3px; font-weight: 600; }}

            .resolved-item {{ opacity: 0.6; }}
            .resolved-item .probe-desc,
            .resolved-item .probe-warning,
            .resolved-item .perturb-action {{ text-decoration: line-through; text-decoration-color: var(--success); }}
            .btn-resolve {{ height: 30px; padding: 0 13px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; font-weight: 600; transition: all 0.15s; border: 1px solid var(--success); color: var(--success-text); background: var(--success-bg); }}
            .btn-resolve:hover {{ background: #d1fae5; border-color: #059669; }}
            .btn-resolve.is-resolved {{ cursor: default; opacity: 0.7; }}
            .status-pill.resolved {{ background: var(--success-bg); color: var(--success-text); border: 1px solid #a7f3d0; }}
            .ledger-resolve-wrap {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); }}

            .trace-exception {{ color: var(--danger); font-weight: 600; }}
        </style>
        <script>
            const fileCache = {file_cache_json};
            window.initialT1Count = {total_t1_unreviewed};
            window.initialT2Count = {total_t2_unreviewed};
            window.totalTestCount = {total_tests};
            window.totalMethodCount = {valid_methods_count};

            const _PROBE_IDS = {probe_ids_json};
            const _STORAGE_KEY = 'perturb_triage_' + _PROBE_IDS.slice().sort().join(',').split('').reduce((h,c)=>((h<<5)-h+c.charCodeAt(0))|0, 0);

            function saveState() {{
                const state = {{}};
                document.querySelectorAll('li[data-probe-id]').forEach(el => {{
                    const pid      = el.getAttribute('data-probe-id');
                    const s        = el.getAttribute('data-state');
                    const tid      = el.getAttribute('data-test-id');
                    const resolved = el.getAttribute('data-resolved') === 'true';
                    const tag      = el.querySelector('.triage-tag') ? el.querySelector('.triage-tag').innerText : null;
                    if (s && s !== 'unreviewed') {{
                        if (!state[pid]) state[pid] = [];
                        state[pid].push({{ testId: tid, decision: s, tag, resolved }});
                    }}
                }});
                document.querySelectorAll('tr[id^="ledger-row-"][data-resolved="true"]').forEach(row => {{
                    const pid = row.id.replace('ledger-row-', '');
                    if (!state[pid]) state[pid] = [];
                    const existing = state[pid].find(e => e.decision === 'ledger-resolved');
                    if (!existing) state[pid].push({{ testId: null, decision: 'ledger-resolved', tag: null, resolved: true }});
                }});
                try {{ localStorage.setItem(_STORAGE_KEY, JSON.stringify(state)); }} catch(e) {{}}
            }}

            function loadState(state) {{
                if (!state) return;
                Object.entries(state).forEach(([pid, entries]) => {{
                    entries.forEach(entry => {{
                        const {{ testId, decision, tag, resolved }} = entry;
                        const tagText = tag ? tag.replace(/^\[\s*|\s*\]$/g, '') : decision;
                        if (decision === 'ledger-resolved') return;
                        if (decision === 'action-code' || decision === 'equivalent-code') {{
                            const el = document.getElementById(`code-probe-${{pid}}`);
                            if (el && el.getAttribute('data-state') !== decision) {{
                                const list = el.closest('ul');
                                const methodId = list ? list.id.replace('list-code-t2-', '') : null;
                                if (methodId) triageCode(methodId, pid, decision, tagText);
                            }}
                        }} else if (testId) {{
                            const el = document.getElementById(`probe-${{testId}}-${{pid}}`);
                            if (el && el.getAttribute('data-state') === 'unreviewed') {{
                                triageTest(testId, pid, decision, tagText);
                            }}
                        }}
                    }});
                }});
                Object.entries(state).forEach(([pid, entries]) => {{
                    entries.forEach(entry => {{
                        const {{ testId, decision, resolved }} = entry;
                        if (!resolved && decision !== 'ledger-resolved') return;
                        if (decision === 'ledger-resolved') {{
                            const btn = document.querySelector(`button[data-resolve-ledger="${{pid}}"]`);
                            if (btn) markResolved(pid, 'ledger', btn);
                        }} else if (decision === 'action-code') {{
                            const btn = document.querySelector(`button[data-resolve-code="${{pid}}"]`);
                            if (btn) markResolved(pid, 'code', btn);
                        }} else if (testId && decision === 'action') {{
                            const btn = document.querySelector(`button[data-resolve-test="${{pid}}-${{testId}}"]`);
                            if (btn) markResolved(pid, `test-${{testId}}`, btn);
                        }}
                    }});
                }});
            }}

            function exportState() {{
                const state = {{}};
                document.querySelectorAll('li[data-probe-id]').forEach(el => {{
                    const pid = el.getAttribute('data-probe-id');
                    const s   = el.getAttribute('data-state');
                    const tid = el.getAttribute('data-test-id');
                    const tag = el.querySelector('.triage-tag') ? el.querySelector('.triage-tag').innerText : null;
                    if (s && s !== 'unreviewed') {{
                        if (!state[pid]) state[pid] = [];
                        state[pid].push({{ testId: tid, decision: s, tag }});
                    }}
                }});
                const blob = new Blob([JSON.stringify({{ version: 1, probeIds: _PROBE_IDS, state }}, null, 2)], {{type: 'application/json'}});
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'triage-state.json';
                a.click();
                URL.revokeObjectURL(a.href);
            }}

            function resetDashboard() {{
                try {{ localStorage.removeItem(_STORAGE_KEY); }} catch(e) {{}}
                location.reload();
            }}

            function importState(file) {{
                if (!file) return;
                const reader = new FileReader();
                reader.onload = e => {{
                    try {{
                        const data = JSON.parse(e.target.result);
                        if (!data.state) {{ showToast('❌ Invalid file — missing state field.', 'error'); return; }}
                        const imported = new Set(data.probeIds || []);
                        const current  = new Set(_PROBE_IDS);
                        const skipped  = [...imported].filter(p => !current.has(p)).length;
                        const restored = Object.keys(data.state).length - skipped;
                        loadState(data.state);
                        saveState();
                        const banner = document.getElementById('import-banner');
                        if (banner) banner.style.display = 'none';
                        let msg = `Imported — ${{restored}} decision${{restored !== 1 ? 's' : ''}} restored.`;
                        if (skipped > 0) msg += ` ${{skipped}} probe${{skipped !== 1 ? 's' : ''}} no longer exist and were skipped.`;
                        showToast(msg, 'success');
                    }} catch(err) {{
                        showToast('Failed to parse triage-state.json: ' + err.message, 'error');
                    }}
                }};
                reader.readAsText(file);
            }}

            function showToast(message, type) {{
                const existing = document.getElementById('_toast');
                if (existing) existing.remove();
                const bg = type === 'error' ? 'var(--danger-bg)' : 'var(--success-bg)';
                const border = type === 'error' ? 'var(--danger)' : 'var(--success)';
                const color = type === 'error' ? 'var(--danger-text)' : 'var(--success-text)';
                const toast = document.createElement('div');
                toast.id = '_toast';
                toast.innerText = message;
                toast.style.cssText = `position:fixed; bottom:24px; right:24px; z-index:9999;
                    background:${{bg}}; color:${{color}}; border:1px solid ${{border}};
                    border-left:4px solid ${{border}}; border-radius:8px;
                    padding:12px 18px; font-size:13px; font-weight:500;
                    box-shadow:0 4px 12px rgba(0,0,0,0.1); max-width:420px;
                    opacity:0; transition:opacity 0.2s ease;`;
                document.body.appendChild(toast);
                requestAnimationFrame(() => {{ toast.style.opacity = '1'; }});
                setTimeout(() => {{
                    toast.style.opacity = '0';
                    setTimeout(() => toast.remove(), 200);
                }}, 4000);
            }}

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
                    const resolveWrap = document.getElementById(`resolve-wrap-${{testId}}-${{probeId}}`);
                    if (resolveWrap) resolveWrap.style.display = 'block';
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
                                ledgerBadge.style.cssText = 'background:#f1f5f9; color:#64748b; border:1px solid #cbd5e1;';
                                ledgerBadge.innerText = 'Discarded';
                            }}
                            updateLedgerCounts();
                        }}
                    }}
                }} else if (decisionType === 'noise') {{
                    probeEl.classList.add('noise-item');
                    const noiseList = document.getElementById(`list-noise-${{testId}}`);
                    const noiseContainer = document.getElementById(`noise-section-${{testId}}`);
                    if(noiseContainer) noiseContainer.style.display = 'block';
                    if(noiseList) noiseList.appendChild(probeEl);
                }}
                updateBadge(testId);
                updateAccordionCounts(testId);
                saveState();
            }}

            function markResolved(probeId, context, btn) {{
                function resolveProbeEl(el) {{
                    if (!el || el.getAttribute('data-resolved') === 'true') return;
                    el.setAttribute('data-resolved', 'true');
                    el.classList.add('resolved-item');
                    const tid = el.getAttribute('data-test-id');
                    if (tid) updateBadge(tid);
                }}
                function flipBtn(b) {{
                    if (!b || b.disabled) return;
                    b.innerHTML = 'Fixed';
                    b.classList.add('is-resolved');
                    b.disabled = true;
                    b.onclick = null;
                }}
                if (context.startsWith('test-')) {{
                    const testId = context.slice(5);
                    const probeEl = document.getElementById(`probe-${{testId}}-${{probeId}}`);
                    resolveProbeEl(probeEl);
                    document.querySelectorAll(`li[data-probe-id="${{probeId}}"]`).forEach(el => {{
                        if (el.id.startsWith('code-probe-')) return;
                        resolveProbeEl(el);
                        const otherTestId = el.getAttribute('data-test-id');
                        if (otherTestId) {{
                            flipBtn(document.querySelector(`button[data-resolve-test="${{probeId}}-${{otherTestId}}"]`));
                        }}
                    }});
                    const ledgerRow = document.getElementById(`ledger-row-${{probeId}}`);
                    if (ledgerRow && ledgerRow.getAttribute('data-resolved') !== 'true') {{
                        ledgerRow.setAttribute('data-resolved', 'true');
                        ledgerRow.style.opacity = '0.6';
                        const badge = document.getElementById(`ledger-badge-${{probeId}}`);
                        if (badge) {{ badge.className = 'badge badge-success'; badge.style.cssText = ''; badge.innerText = 'Fixed'; }}
                        flipBtn(document.querySelector(`button[data-resolve-ledger="${{probeId}}"]`));
                    }}
                }} else if (context === 'code') {{
                    const probeEl = document.getElementById(`code-probe-${{probeId}}`);
                    resolveProbeEl(probeEl);
                    if (probeEl) {{
                        const list = probeEl.closest('ul');
                        if (list) updateCodeBadge(list.id.replace('list-code-t2-', ''));
                    }}
                }} else if (context === 'ledger') {{
                    const row = document.getElementById(`ledger-row-${{probeId}}`);
                    if (row) {{
                        row.setAttribute('data-resolved', 'true');
                        row.style.opacity = '0.6';
                        const badge = document.getElementById(`ledger-badge-${{probeId}}`);
                        if (badge) {{ badge.className = 'badge badge-success'; badge.style.cssText = ''; badge.innerText = 'Fixed'; }}
                    }}
                }}
                flipBtn(btn);
                saveState();
            }}

            let _bulkState = {{ testId: null, groups: {{}} }};

            function openBulkTriageModal(testId, testFqcn) {{
                const survivedList = document.getElementById(`list-t1-${{testId}}`);
                if (!survivedList) return;
                const unreviewed = Array.from(survivedList.querySelectorAll('li[data-state="unreviewed"]'));
                if (unreviewed.length === 0) {{
                    showToast('No unreviewed probes remaining in this test.', 'success');
                    return;
                }}
                const groups = {{}};
                unreviewed.forEach(probeEl => {{
                    const fqcn = probeEl.getAttribute('data-target-fqcn') || 'unknown';
                    if (!groups[fqcn]) groups[fqcn] = [];
                    groups[fqcn].push({{
                        probeId: probeEl.getAttribute('data-probe-id'),
                        desc: probeEl.querySelector('.probe-desc') ? probeEl.querySelector('.probe-desc').textContent.trim() : ''
                    }});
                }});
                _bulkState = {{ testId, groups }};
                const sortedFqcns = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
                const totalProbes = unreviewed.length;
                const testShortName = testFqcn.split('.').pop();
                document.getElementById('bulkModalTitle').innerText = `Bulk Triage — ${{testShortName}}`;
                document.getElementById('bulkModalSubtitle').innerText =
                    `${{totalProbes}} unreviewed probe${{totalProbes !== 1 ? 's' : ''}} across ${{sortedFqcns.length}} target class${{sortedFqcns.length !== 1 ? 'es' : ''}}`;
                let treeHtml = '';
                sortedFqcns.forEach((fqcn, idx) => {{
                    const probes = groups[fqcn];
                    const shortClass = fqcn === 'unknown' ? 'Unknown' : fqcn.split('.').pop();
                    const pkg = fqcn === 'unknown' ? '' : fqcn.split('.').slice(0, -1).join('.');
                    const nodeId = `bulk-node-${{idx}}`;
                    const isFirst = idx === 0;
                    const probeRows = probes.map(p => `
                        <div class="bulk-probe-row" data-probe-id="${{p.probeId}}">
                            <label style="display:flex; align-items:flex-start; gap:10px; padding:6px 8px; border-radius:var(--radius-sm); cursor:pointer; transition:background 0.1s;"
                                   onmouseover="this.style.background='#f1f5f9'" onmouseout="this.style.background='transparent'">
                                <input type="checkbox" checked data-probe="${{p.probeId}}" data-fqcn="${{fqcn}}"
                                       style="width:15px;height:15px;flex-shrink:0;margin-top:2px;accent-color:var(--primary);cursor:pointer;">
                                <span style="font-family:ui-monospace,monospace;font-size:12px;color:var(--text-muted);line-height:1.4;">${{p.desc}}</span>
                            </label>
                        </div>`).join('');
                    treeHtml += `
                    <div class="bulk-class-node" style="border:1px solid var(--border-color);border-radius:var(--radius-md);overflow:hidden;margin-bottom:8px;">
                        <div class="bulk-node-header" style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#f8fafc;cursor:pointer;user-select:none;"
                             onclick="toggleBulkNode('${{nodeId}}', this)">
                            <span class="bulk-toggle-icon" style="font-size:11px;width:14px;flex-shrink:0;color:var(--text-muted);">${{isFirst ? '▼' : '▶'}}</span>
                            <input type="checkbox" checked data-class-fqcn="${{fqcn}}"
                                   style="width:16px;height:16px;accent-color:var(--primary);cursor:pointer;flex-shrink:0;"
                                   onclick="event.stopPropagation(); toggleClassCheck(this, '${{fqcn}}')">
                            <div style="flex:1;min-width:0;">
                                <div style="font-weight:700;font-size:14px;color:var(--text-main);">${{shortClass}}</div>
                                ${{pkg ? `<div style="font-family:ui-monospace,monospace;font-size:11px;color:var(--text-muted);margin-top:1px;">${{pkg}}</div>` : ''}}
                            </div>
                            <span style="font-size:12px;font-weight:600;color:var(--text-muted);background:#e2e8f0;padding:3px 10px;border-radius:9999px;white-space:nowrap;flex-shrink:0;">${{probes.length}} probe${{probes.length !== 1 ? 's' : ''}}</span>
                        </div>
                        <div id="${{nodeId}}" style="display:${{isFirst ? 'block' : 'none'}};padding:6px 14px 10px 14px;background:#fff;border-top:1px solid var(--border-color);">
                            ${{probeRows}}
                        </div>
                    </div>`;
                }});
                document.getElementById('bulkModalTree').innerHTML = treeHtml;
                document.getElementById('bulkModal').style.display = 'block';
                document.body.style.overflow = 'hidden';
            }}

            function toggleBulkNode(nodeId, header) {{
                const content = document.getElementById(nodeId);
                const icon = header.querySelector('.bulk-toggle-icon');
                const isOpen = content.style.display !== 'none';
                content.style.display = isOpen ? 'none' : 'block';
                icon.textContent = isOpen ? '▶' : '▼';
            }}

            function toggleClassCheck(masterCb, fqcn) {{
                document.querySelectorAll(`#bulkModalTree input[data-fqcn="${{fqcn}}"][data-probe]`).forEach(cb => {{
                    cb.checked = masterCb.checked;
                }});
            }}

            function confirmBulkTriage() {{
                const {{ testId, groups }} = _bulkState;
                const checkboxes = document.querySelectorAll('#bulkModalTree input[data-probe]');
                let count = 0;
                checkboxes.forEach(cb => {{
                    if (cb.checked) {{
                        triageTest(testId, cb.getAttribute('data-probe'), 'noise', 'Out of Scope (Bulk Triage)');
                        count++;
                    }}
                }});
                closeBulkModal();
                if (count > 0) showToast(`${{count}} probe${{count !== 1 ? 's' : ''}} marked as Out of Scope.`, 'success');
            }}

            function closeBulkModal() {{
                document.getElementById('bulkModal').style.display = 'none';
                document.body.style.overflow = 'auto';
                _bulkState = {{ testId: null, groups: {{}} }};
            }}

            function closeSweepModal() {{ closeBulkModal(); }}

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
                        const codeResolveWrap = document.getElementById(`code-resolve-wrap-${{probeId}}`);
                        if (codeResolveWrap) codeResolveWrap.style.display = 'block';
                    }} else if (decisionType === 'equivalent-code') {{
                        codeProbeEl.classList.add('noise-item');
                        codeProbeEl.classList.remove('action-required');
                        const noiseList = document.getElementById(`list-code-noise-${{methodId}}`);
                        const noiseContainer = document.getElementById(`code-noise-section-${{methodId}}`);
                        if(noiseContainer) noiseContainer.style.display = 'block';
                        if(noiseList) noiseList.appendChild(codeProbeEl);
                    }}
                }}
                updateCodeAccordionCounts(methodId);
                updateCodeBadge(methodId);
                saveState();
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
                const resolvedCode = methodContainer.querySelectorAll('li.probe-item[data-state="action-code"][data-resolved="true"]').length;
                const pendingAction = needsAction - resolvedCode;
                if (unreviewed === 0 && pendingAction === 0 && resolvedCode > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill resolved">[ ${{resolvedCode}} Fixed ]</span>`;
                }} else if (unreviewed === 0 && pendingAction === 0) {{
                    badgeEl.innerHTML = `<span class="status-pill clear">[ Fully Triaged & Clear ]</span>`;
                }} else if (unreviewed === 0 && pendingAction > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill action">[ Fully Triaged | ${{pendingAction}} Need Action ]</span>`;
                }} else if (unreviewed > 0 && pendingAction > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill mid">[ ${{unreviewed}} Unreviewed | ${{pendingAction}} Need Action ]</span>`;
                }} else {{
                    badgeEl.innerHTML = `<span class="status-pill pending">[ ${{unreviewed}} Unreviewed ]</span>`;
                }}
                const t2UnreviewedGlobal = document.querySelectorAll('#code-view li.probe-item[data-state="unreviewed"]').length;
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
                        const count = tbody.children.length / 2;
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
                const unreviewed  = testContainer.querySelectorAll('li[data-state="unreviewed"]').length;
                const needsAction = testContainer.querySelectorAll('li[data-state="action"]:not([data-resolved="true"])').length;
                const resolved    = testContainer.querySelectorAll('li[data-state="action"][data-resolved="true"]').length;
                const badgeEl = document.getElementById(`badge-${{testId}}`);
                if (unreviewed === 0 && needsAction === 0 && resolved > 0) {{
                    badgeEl.innerHTML = `<span class="status-pill resolved">[ ${{resolved}} Fixed ]</span>`;
                }} else if (unreviewed === 0 && needsAction === 0) {{
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
                const t1Unreviewed = document.querySelectorAll('#test-view li[data-tier="1"][data-state="unreviewed"]').length;
                const confirmedBugs = document.querySelectorAll('#test-view li[data-state="action"]').length;
                const noiseBugs = document.querySelectorAll('#test-view li[data-state="equivalent"], #test-view li[data-state="noise"]').length;
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
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:24px; gap:16px; flex-wrap:wrap;">
                <h1>Perturbation Analysis Dashboard</h1>
                <div style="display:flex; gap:6px; align-items:center; flex-shrink:0;">
                    <input type="file" id="import-file-input" accept=".json" style="display:none;">
                    <button class="btn-small" onclick="document.getElementById('import-file-input').click()"
                            title="Load a previously exported triage-state.json to restore decisions">
                        Import Progress
                    </button>
                    <button class="btn-small" onclick="exportState()"
                            title="Download current triage decisions as triage-state.json">
                        Export Progress
                    </button>
                    <button class="btn-small" style="color: var(--danger); border-color: #fca5a5;"
                            onclick="resetDashboard()"
                            title="Reset all triage decisions and reload the page">
                        Reset
                    </button>
                </div>
            </div>
            <div id="import-banner" style="margin-bottom:20px; padding:11px 16px; background:var(--warning-bg); border:1px solid #fde68a; border-left:3px solid var(--warning); border-radius:var(--radius-md); font-size:12px; color:var(--warning-text); display:flex; align-items:center; justify-content:space-between; gap:12px;">
                <span><strong>No saved progress found.</strong> If you have a previous <code>triage-state.json</code>, click <strong>Import Progress</strong> to restore your triage decisions.</span>
                <button class="btn-small" style="flex-shrink:0;" onclick="document.getElementById('import-banner').style.display='none'">Dismiss</button>
            </div>

            <div id="metrics-test" class="metrics-container active">
                <div class="metric-card">
                    <div class="metric-value" id="ui-t1-inbox">{total_t1_unreviewed} / {total_t1_unreviewed}</div>
                    <div class="metric-label">Unreviewed Survivals</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" id="ui-t1-action">0</div>
                    <div class="metric-label">Confirmed Weak Tests</div>
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
                    <div class="metric-value">{metrics['total_discovered']}</div>
                    <div class="metric-label">Total Probes</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['clean_kills']}</div>
                    <div class="metric-label">Clean Kills</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['dirty_kills']}</div>
                    <div class="metric-label">Dirty Kills / Timeouts</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['survivals']}</div>
                    <div class="metric-label">Survivals (Unprotected)</div>
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
                <div class="tab active" onclick="switchTab('test-view')">Test-Centric</div>
                <div class="tab" onclick="switchTab('probe-view')">Probe-Centric</div>
                <div class="tab" onclick="switchTab('code-view')">Code-Centric</div>
            </div>

            <div id="test-view" class="tab-content active">
                <div class="tab-header">
                    <h2>Test-Centric</h2>
                    <p>Every test, its full probe footprint, and triage status. Expand a row to review and classify surviving probes.</p>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Test Name</th>
                                <th class="text-center" style="width: 180px;">Footprint</th>
                                <th class="text-right" style="width: 260px;">Triage Status</th>
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
                    <h2>Probe-Centric</h2>
                    <p>Every injected probe, its outcome, and how many tests witnessed it. Un-hit probes indicate dead or unreachable code.</p>
                </div>
                <div style="padding: 0;">
                    {ledger_html}
                </div>
            </div>

            <div id="code-view" class="tab-content">
                <div class="tab-header">
                    <h2>Code-Centric</h2>
                    <p>Production code that crashes when perturbed. Grouped by method; each probe shows the full per-test outcome breakdown.</p>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Target Method</th>
                                <th class="text-center" style="width: 200px;">Execution Failures</th>
                                <th class="text-right" style="width: 320px;">Triage Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {code_rows}
                        </tbody>
                    </table>
                </div>
            </div>

        </div>

        <div id="bulkModal" class="modal" onclick="if(event.target===this) closeBulkModal()">
            <div class="modal-content" style="width: 620px; height: auto; max-height: 82vh; margin: 5% auto; display:flex; flex-direction:column;">
                <div class="modal-header">
                    <div>
                        <h2 id="bulkModalTitle" style="margin:0 0 2px 0;">Bulk Triage</h2>
                        <div id="bulkModalSubtitle" style="font-size:13px; color:var(--text-muted); font-weight:400;"></div>
                    </div>
                    <span class="close" onclick="closeBulkModal()">&times;</span>
                </div>
                <p style="margin: 0 0 14px 0; font-size:13px; color:var(--text-muted); line-height:1.5;">
                    Probes are grouped by the class they target. Expand a class to review individual probes.
                    Checked probes will be marked <strong>Out of Scope</strong> on confirm.
                </p>
                <div id="bulkModalTree" style="flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:0; min-height:0;"></div>
                <div style="display:flex; gap:10px; justify-content:flex-end; margin-top:16px; padding-top:16px; border-top:1px solid var(--border-color);">
                    <button class="btn-small" onclick="closeBulkModal()">Cancel</button>
                    <button class="btn-primary" onclick="confirmBulkTriage()">Confirm Triage</button>
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

            document.addEventListener('DOMContentLoaded', () => {{
                try {{
                    const saved = localStorage.getItem(_STORAGE_KEY);
                    if (saved) {{
                        loadState(JSON.parse(saved));
                        const banner = document.getElementById('import-banner');
                        if (banner) banner.style.display = 'none';
                    }}
                }} catch(e) {{}}

                const fileInput = document.getElementById('import-file-input');
                if (fileInput) {{
                    fileInput.addEventListener('change', e => {{
                        importState(e.target.files[0]);
                        fileInput.value = '';
                    }});
                }}
            }});

            function renderAndHighlight(containerId, code, methodName) {{
                const container = document.getElementById(containerId);
                if (!code) {{
                    container.innerHTML = "<pre><code>// File content not available or could not be read.</code></pre>";
                    return;
                }}
                let escapedCode = code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                container.innerHTML = `<pre><code class="language-java">${{escapedCode}}</code></pre>`;
                hljs.highlightElement(container.querySelector('code'));
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
                const codeModal = document.getElementById('codeModal');
                if (event.target == codeModal) closeModal();
                const bulkModal = document.getElementById('bulkModal');
                if (event.target == bulkModal) closeBulkModal();
            }}

            document.addEventListener('keydown', function(event) {{
                if (event.key === "Escape") {{
                    closeModal();
                    closeBulkModal();
                }}
            }});
        </script>
    </body>
    </html>
    """

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return html_path
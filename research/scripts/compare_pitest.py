import xml.etree.ElementTree as ET
import json
from collections import defaultdict
import os

PROJECT_XML_MAP = {
    "JSemVer":           "data/mutations-jsemver.xml",
    "Joda-Money":        "data/mutations-joda-money.xml",
    "Commons-CLI":       "data/mutations-commons-cli.xml",
    "Commons-CSV":       "data/mutations-commons-csv.xml",
    "Commons-Validator": "data/mutations-commons-validator.xml",
}

PERTURB_JSON_PATH = "../data/database.json"

PITEST_KILL_STATUSES  = {'KILLED', 'TIMED_OUT', 'MEMORY_ERROR', 'RUN_ERROR'}
PERTURB_KILL_STATUSES = {'Clean Kill', 'Dirty Kill', 'TIMEOUT'}

DISPLAY_LIMIT = 20


def load_pitest_data(xml_path):
    stats = defaultdict(lambda: {'killed': 0, 'total': 0, 'unhit': 0})
    if not os.path.exists(xml_path):
        print(f"WARNING: PITest XML not found: {xml_path}")
        return stats

    for mutation in ET.parse(xml_path).getroot().findall('mutation'):
        key = ".".join([
            mutation.find('mutatedClass').text,
            mutation.find('mutatedMethod').text,
            mutation.find('methodDescription').text,
        ])
        stats[key]['total'] += 1

        status = mutation.get('status')
        if status in PITEST_KILL_STATUSES:
            stats[key]['killed'] += 1
        elif status == 'NO_COVERAGE':
            stats[key]['unhit'] += 1

    return stats


def load_all_perturb_data(json_path):
    db_by_project = defaultdict(lambda: defaultdict(lambda: {'killed': 0, 'total': 0, 'unhit': 0}))

    if not os.path.exists(json_path):
        print(f"WARNING: Perturbation JSON not found: {json_path}")
        return db_by_project

    with open(json_path, 'r') as f:
        db = json.load(f)

    for probe in db.get('probes', []):
        project = probe.get('project')
        outcome = probe.get('probe_outcome')

        if not project or not outcome:
            continue

        c_name = probe.get('fqcn') or probe.get('targetClass')
        m_name = probe.get('method') or probe.get('targetMethod')
        desc   = probe.get('asmDescriptor') or probe.get('descriptor') or ""

        if not c_name or not m_name:
            continue

        c_name = c_name.replace('/', '.')

        # Normalise constructors to <init> to match PITest's representation.
        if m_name == c_name.split('.')[-1]:
            m_name = "<init>"

        key = f"{c_name}.{m_name}.{desc}".strip('.')
        db_by_project[project][key]['total'] += 1

        if outcome in PERTURB_KILL_STATUSES:
            db_by_project[project][key]['killed'] += 1
        elif outcome == 'Un-hit':
            db_by_project[project][key]['unhit'] += 1

    return db_by_project


def _parse_single_jvm_type(s, index):
    array_dims = 0
    while index < len(s) and s[index] == '[':
        array_dims += 1
        index += 1

    if index >= len(s):
        return "", index

    char = s[index]

    if char == 'L':
        end = s.find(';', index)
        class_name = s[index + 1:end].split('/')[-1].split('$')[-1]
        index = end + 1
        return class_name + ('[]' * array_dims), index

    primitives = {
        'Z': 'boolean', 'B': 'byte',  'C': 'char',  'S': 'short',
        'I': 'int',     'J': 'long',  'F': 'float', 'D': 'double', 'V': 'void',
    }
    ptype = primitives.get(char, char)
    index += 1
    return ptype + ('[]' * array_dims), index


def parse_jvm_descriptor(desc):
    if not desc or not desc.startswith('('):
        return "", ""

    paren_idx = desc.find(')')
    args_str  = desc[1:paren_idx]
    ret_str   = desc[paren_idx + 1:]

    args = []
    i = 0
    while i < len(args_str):
        java_type, i = _parse_single_jvm_type(args_str, i)
        if java_type:
            args.append(java_type)

    ret_type, _ = _parse_single_jvm_type(ret_str, 0)
    return ", ".join(args), ret_type


def format_signature(full_key):
    parts = full_key.split('.')
    if len(parts) < 3:
        return full_key

    desc        = parts[-1]
    method_name = parts[-2]
    class_name  = parts[-3].split('$')[-1]

    args_str, ret_type = parse_jvm_descriptor(desc)

    if method_name == "<init>":
        return f"[Constructor] {class_name}({args_str})"

    return f"{ret_type} {class_name}.{method_name}({args_str})"


def _kill_score(stats, key):
    if key not in stats:
        return None
    killed = stats[key]['killed']
    total  = stats[key]['total']
    unhit  = stats[key]['unhit']

    if total > 0 and unhit == total:
        return f"{killed}/{total} (Un-hit)"

    pct = int((killed / total) * 100) if total > 0 else 0
    return f"{killed}/{total} ({pct}%)"


def print_method_table(title, keys, pitest_stats, perturb_stats, limit=DISPLAY_LIMIT):
    if not keys:
        return

    visible   = sorted(keys)[:limit]
    col_width = max((len(format_signature(k)) for k in visible), default=52)

    sep = '-' * (col_width + 34)
    print(f"\n{sep}")
    print(f"  {title}  [{min(len(keys), limit)} of {len(keys)}]")
    print(sep)
    print(f"  {'Method':<{col_width}}  {'PITest':>13}  {'Perturb':>13}")
    print(f"  {'-' * col_width}  {'-' * 13}  {'-' * 13}")

    for key in visible:
        signature = format_signature(key)
        p_score   = _kill_score(pitest_stats,  key) or "n/a"
        q_score   = _kill_score(perturb_stats, key) or "n/a"
        print(f"  {signature:<{col_width}}  {p_score:>13}  {q_score:>13}")

    if len(keys) > limit:
        print(f"  ... and {len(keys) - limit} more.")
    print()


def analyze_all_projects():
    sep = "=" * 90

    print(sep)
    print("  MULTI-PROJECT OVERLAP ANALYSIS")
    print(sep)

    all_perturb_data = load_all_perturb_data(PERTURB_JSON_PATH)

    for project_name, xml_path in PROJECT_XML_MAP.items():
        print(f"\n{sep}")
        print(f"  PROJECT: {project_name}")
        print(sep)

        pitest_data  = load_pitest_data(xml_path)
        perturb_data = all_perturb_data.get(project_name, {})

        pitest_keys  = set(pitest_data.keys())
        perturb_keys = set(perturb_data.keys())

        pitest_only  = pitest_keys - perturb_keys
        perturb_only = perturb_keys - pitest_keys
        overlapping  = pitest_keys & perturb_keys

        print(f"  PITest methods:        {len(pitest_keys):>4}")
        print(f"  Perturbation methods:  {len(perturb_keys):>4}")
        print(f"  Overlapping methods:   {len(overlapping):>4}")

        if not pitest_keys and not perturb_keys:
            print("  No data found for this project. Skipping.")
            continue

        if pitest_only:
            print_method_table(
                "PITEST ONLY  (no matching perturbation probe)",
                pitest_only, pitest_data, perturb_data,
            )
        if perturb_only:
            print_method_table(
                "PERTURBATION ONLY  (no matching PITest mutation)",
                perturb_only, pitest_data, perturb_data,
            )

        if overlapping:
            cat_mutual_blind   = []
            cat_mutual_success = []
            cat_perturb_adv    = []
            cat_pitest_adv     = []
            cat_mixed          = []

            for key in overlapping:
                p_tot = pitest_data[key]['total']
                q_tot = perturb_data[key]['total']
                p_pct = int((pitest_data[key]['killed']  / p_tot) * 100) if p_tot > 0 else 0
                q_pct = int((perturb_data[key]['killed'] / q_tot) * 100) if q_tot > 0 else 0

                if p_pct == 0 and q_pct == 0:
                    cat_mutual_blind.append(key)
                elif p_pct == 100 and q_pct == 100:
                    cat_mutual_success.append(key)
                elif p_pct == 0 and q_pct > 0:
                    cat_perturb_adv.append(key)
                elif q_pct == 0 and p_pct > 0:
                    cat_pitest_adv.append(key)
                else:
                    cat_mixed.append(key)

            print(f"\n  --- OVERLAP BREAKDOWN ---")
            print_method_table("1. MUTUAL BLIND SPOTS (both 0%)",                     cat_mutual_blind,    pitest_data, perturb_data)
            print_method_table("2. PERTURBATION ADVANTAGE (PITest 0%, Perturb > 0%)", cat_perturb_adv,    pitest_data, perturb_data)
            print_method_table("3. PITEST ADVANTAGE (Perturb 0%, PITest > 0%)",       cat_pitest_adv,     pitest_data, perturb_data)
            print_method_table("4. MIXED / PARTIAL",                                  cat_mixed,          pitest_data, perturb_data)
            print_method_table("5. MUTUAL SUCCESS (both 100%)",                       cat_mutual_success, pitest_data, perturb_data)


if __name__ == "__main__":
    analyze_all_projects()
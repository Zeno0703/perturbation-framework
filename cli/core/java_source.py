import os

from .artifact_reader import parse_probe
from .config import SRC_MAIN_JAVA, SRC_TEST_JAVA


def get_java_file_path(project_dir, fqcn, is_test=False):
    if not fqcn or fqcn == "unknown":
        return None
    base_class = fqcn.split('$')[0]
    rel_path = base_class.replace('.', '/') + ".java"
    base_dir = SRC_TEST_JAVA if is_test else SRC_MAIN_JAVA
    return os.path.join(project_dir, base_dir, rel_path)


def read_java_file(project_dir, fqcn, is_test=False):
    path = get_java_file_path(project_dir, fqcn, is_test)
    if not path or not os.path.exists(path):
        return f"// Source file not found: {path}"
    try:
        with open(path, encoding="utf-8") as source_file:
            return source_file.read()
    except Exception as exc:
        return f"// Error reading file: {exc}"


def to_idea_link(project_dir, fqcn, is_test=False):
    path = get_java_file_path(project_dir, fqcn, is_test)
    if not path:
        return "#"
    return f"idea://open?file={os.path.abspath(path)}"


def build_file_cache(project_dir, test_stats, dashboard_ledger, dashboard_methods):
    file_cache = {}
    needed_files = set()

    for test_name, test_data in test_stats.items():
        test_class = test_name.split('#')[0]
        needed_files.add((test_class, True))
        for probe in test_data["probes"]:
            _, fqcn, _, _, _ = parse_probe(probe["desc"])
            if fqcn != "unknown":
                needed_files.add((fqcn, False))

    for probe in dashboard_ledger:
        if probe["fqcn"] and probe["fqcn"] != "unknown":
            needed_files.add((probe["fqcn"], False))

    for method_data in dashboard_methods.values():
        if method_data["fqcn"] and method_data["fqcn"] != "unknown":
            needed_files.add((method_data["fqcn"], False))

    raw_cache = {}
    for fqcn, is_test in needed_files:
        raw_cache[(fqcn, is_test)] = read_java_file(project_dir, fqcn, is_test)

    serialisable_cache = {}
    for (fqcn, is_test), content in raw_cache.items():
        # If a test class and production class collide on key, we keep the production source.
        if fqcn not in serialisable_cache or not is_test:
            serialisable_cache[fqcn] = content

    return serialisable_cache
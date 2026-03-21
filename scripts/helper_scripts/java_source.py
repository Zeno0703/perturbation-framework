import os

try:
    from probe_analyser import parse_probe
except ModuleNotFoundError:
    from .probe_analyser import parse_probe


def get_java_file_path(project_dir, fqcn, is_test=False):
    """
    Resolve the filesystem path for a fully-qualified Java class name.

    Parameters
    ----------
    project_dir : str  — Maven project root.
    fqcn        : str  — Fully-qualified class name (may include inner-class '$').
    is_test     : bool — True → src/test/java, False → src/main/java.

    Returns None when fqcn is falsy or 'unknown'.
    """
    if not fqcn or fqcn == "unknown":
        return None
    base_class = fqcn.split('$')[0]
    rel_path = base_class.replace('.', '/') + ".java"
    base_dir = "src/test/java" if is_test else "src/main/java"
    return os.path.join(project_dir, base_dir, rel_path)


def read_java_file(project_dir, fqcn, is_test=False):
    """
    Return the raw source text of a Java class file.

    Falls back to a comment string when the file cannot be found or read.
    """
    path = get_java_file_path(project_dir, fqcn, is_test)
    if not path or not os.path.exists(path):
        return f"// Source file not found: {path}"
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"// Error reading file: {str(e)}"


def to_idea_link(project_dir, fqcn, is_test=False):
    """
    Build an IntelliJ IDEA deep-link URL for a class file.

    Returns '#' when the class is unknown.
    """
    path = get_java_file_path(project_dir, fqcn, is_test)
    if not path:
        return "#"
    return f"idea://open?file={os.path.abspath(path)}"


def build_file_cache(project_dir, test_stats, dashboard_ledger, dashboard_methods):
    """
    Pre-load all Java source files referenced by the dashboard into a dict.

    Returns
    -------
    dict mapping fqcn (str) -> source text (str).
    Source files take priority over test files for the same fqcn.
    """

    file_cache = {}
    needed_files = set()

    for test_name, stats in test_stats.items():
        test_class = test_name.split('#')[0]
        needed_files.add((test_class, True))
        for p in stats['probes']:
            _, fqcn, _, _, _ = parse_probe(p['desc'])
            if fqcn != "unknown":
                needed_files.add((fqcn, False))

    for p in dashboard_ledger:
        if p['fqcn'] and p['fqcn'] != "unknown":
            needed_files.add((p['fqcn'], False))

    for method_key, stats in dashboard_methods.items():
        if stats['fqcn'] and stats['fqcn'] != "unknown":
            needed_files.add((stats['fqcn'], False))

    raw_cache = {}
    for fqcn, is_test in needed_files:
        raw_cache[(fqcn, is_test)] = read_java_file(project_dir, fqcn, is_test)

    # Source files take priority over test files when the fqcn is shared
    serialisable_cache = {}
    for (fqcn, is_test), content in raw_cache.items():
        if fqcn not in serialisable_cache or not is_test:
            serialisable_cache[fqcn] = content

    return serialisable_cache
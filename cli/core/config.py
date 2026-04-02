import os

OUT_DIR_NAME = "target/perturb"
SRC_MAIN_JAVA = os.path.join("src", "main", "java")
SRC_TEST_JAVA = os.path.join("src", "test", "java")

FILE_PROBES = "probes.txt"
FILE_HITS = "hits.txt"
FILE_OUTCOMES = "test-outcomes.txt"
FILE_PERTURBATIONS = "perturbations.txt"
FILE_METHOD_LINES = "method_lines.properties"

FILE_DASHBOARD = "dashboard.html"
FILE_CACHE_JS = "source_cache.js"

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "research", "data", "database.json"))


def get_out_dir(project_dir):
    return os.path.join(project_dir, OUT_DIR_NAME)
# Perturbation Agent

This tool uses a Java agent to dynamically perturbate state during test execution to identify weak test assertions, missing tests and brittle code. The entire process (including discovery, targeted evaluation, and dashboard generation) is automated via a Python script.

## 1. Build the Agent

Before running the analysis, you need to compile and package the Java agent into a `.jar` file.

```bash
mvn clean package

```

*This will generate `perturb-agent-1.0-SNAPSHOT.jar` in your `target/` directory.*

## 2. Run the Analysis & Dashboard Generator

The main entry point for the tool is the `run_agent_web.py` script. It automatically orchestrates the Maven test runs, collects the outcomes, and generates a standalone HTML dashboard.

### Usage

```bash
python3 run_agent_web.py <path_to_project_dir> <path_to_agent_jar> <target_package>

```

**Arguments:**

1. `<path_to_project_dir>`: The absolute path to the target Maven project you want to test.
2. `<path_to_agent_jar>`: The absolute path to your built perturbation agent `.jar`.
3. `<target_package>`: The base Java package to instrument (e.g., `org.example`).

## 3. Headless Analysis (CLI)

If you want to run the exact same analysis pipeline without generating the HTML dashboard, use `run_agent_cli.py`. This is ideal for when you only want the raw log files and data artifacts.

### Usage

```bash
python3 run_agent_cli.py <path_to_project_dir> <path_to_agent_jar> <target_package> [--discovery-only]

```

### Discovery-Only Mode

If you append the `--discovery-only` flag, the script will only execute the initial probe discovery run (activating probe `-1`). It will write the `probes.txt` and `hits.txt` artifacts to the output folder and then exit, completely skipping the lengthy evaluation phase.

## 4. Output Artifacts

Regardless of whether you use the Web or CLI script, all generated artifacts are saved inside the target project directory under:
`target/perturb/`

These artifacts include:

* `execution.log`: The raw terminal output and diagnostic warnings from the analysis run.
* `probes.txt`: Discovered probes and their descriptions.
* `hits.txt`: Mapping of which tests hit which probes during discovery.
* `test-outcomes.txt` & `perturbations.txt`: Per-test pass/fail states and execution traces.
* `dashboard.html` & `source_cache.js` *(Web Script only)*: The interactive UI and its source code cache.
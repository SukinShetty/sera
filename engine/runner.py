"""
engine/runner.py — Experiment execution engine for SERA.

Public API:
    attach_script(client, experiment_id, script_path) -> Path
        Copies an executable Python script into the client's experiments/
        folder and records it in the experiment's frontmatter.

    run(client, experiment_id, timeout=300) -> dict
        Executes the attached script via subprocess, parses the SERA_METRICS
        contract line from its stdout, logs one result per condition, selects
        the winner, and writes a run log. Returns a run summary dict.

Execution contract for attached scripts:
    - The script is run as `python <script>` in its own process (no import).
    - It must exit 0 on success.
    - Its FINAL stdout line must be:
        SERA_METRICS {"metric": "<name>", "conditions": {"<label>": <value>, ...}}
      where each condition value is numeric. One result file is logged per
      condition and the highest value wins.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown

METRICS_PREFIX = "SERA_METRICS"


def attach_script(client: str, experiment_id: str, script_path) -> Path:
    """
    Attach an executable script to an existing experiment.

    Args:
        client:        Client slug (e.g. "acme-corp").
        experiment_id: Experiment to attach to (e.g. "exp-001"), without .md.
        script_path:   Path to the Python script implementing the experiment.

    Returns:
        Path to the copied script inside the client's experiments/ folder.

    Raises:
        FileNotFoundError: If the script or the experiment file does not exist.
    """
    script_path = Path(script_path)
    if not script_path.exists():
        raise FileNotFoundError(
            f"\n[SERA Runner] Script not found:\n  {script_path}\n"
            "Please check the path and try again."
        )

    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    exp_path = clients_root / client / "experiments" / f"{experiment_id}.md"
    fm, body = read_markdown(exp_path)  # raises FileNotFoundError if missing

    exp_dir = exp_path.parent
    dest = exp_dir / f"{experiment_id}_script.py"
    shutil.copyfile(script_path, dest)

    fm["script"] = dest.name
    write_markdown(exp_path, body, fm)
    return dest


def run(client: str, experiment_id: str, timeout: int = 300) -> dict:
    """
    Execute an experiment's attached script and record its results.

    Args:
        client:        Client slug (e.g. "acme-corp").
        experiment_id: Experiment to run (e.g. "exp-001").
        timeout:       Max seconds to allow the script to run.

    Returns:
        Dict with keys: experiment_id, metric, conditions, result_ids,
        winner (select_winner summary), log_path, exit_code.

    Raises:
        ValueError:        If the experiment has no attached script.
        FileNotFoundError: If the experiment file or attached script is missing.
        RuntimeError:      If the script fails, times out, or violates the
                           SERA_METRICS output contract.
    """
    from engine.results import log_result  # local imports to avoid circular
    from engine.winner import select_winner

    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    exp_path = clients_root / client / "experiments" / f"{experiment_id}.md"
    fm, _ = read_markdown(exp_path)

    script_name = fm.get("script")
    if not script_name:
        raise ValueError(
            f"\n[SERA Runner] Experiment '{experiment_id}' of client '{client}' "
            "has no attached script.\n"
            "Attach one first with engine.runner.attach_script()."
        )

    script_path = exp_path.parent / script_name
    if not script_path.exists():
        raise FileNotFoundError(
            f"\n[SERA Runner] Attached script is missing on disk:\n  {script_path}\n"
            "Re-attach it with engine.runner.attach_script()."
        )

    cmd = [sys.executable, str(script_path)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=str(script_path.parent),
        )
        stdout, stderr, exit_code = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\n[SERA Runner] Timed out after {timeout}s."
        log_path = _write_run_log(client, experiment_id, cmd, "timeout", stdout, stderr)
        raise RuntimeError(
            f"\n[SERA Runner] Experiment '{experiment_id}' timed out after {timeout}s.\n"
            f"Run log: {log_path}"
        ) from exc

    log_path = _write_run_log(client, experiment_id, cmd, exit_code, stdout, stderr)

    if exit_code != 0:
        raise RuntimeError(
            f"\n[SERA Runner] Script for experiment '{experiment_id}' exited with "
            f"code {exit_code}.\nRun log: {log_path}"
        )

    metric, conditions = _parse_metrics(stdout, experiment_id, log_path)

    result_ids = [
        log_result(client, experiment_id, condition, metric, float(value))
        for condition, value in conditions.items()
    ]
    winner_summary = select_winner(client, experiment_id)

    return {
        "experiment_id": experiment_id,
        "metric": metric,
        "conditions": conditions,
        "result_ids": result_ids,
        "winner": winner_summary,
        "log_path": log_path,
        "exit_code": exit_code,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_metrics(stdout: str, experiment_id: str, log_path: Path) -> tuple:
    """Extract (metric, conditions) from the script's final SERA_METRICS line."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines or not lines[-1].startswith(METRICS_PREFIX):
        raise RuntimeError(
            f"\n[SERA Runner] Script for experiment '{experiment_id}' did not end "
            f"with a {METRICS_PREFIX} line.\nRun log: {log_path}"
        )

    payload = lines[-1][len(METRICS_PREFIX):].lstrip(":").strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"\n[SERA Runner] {METRICS_PREFIX} line is not valid JSON: {payload[:200]}\n"
            f"Run log: {log_path}"
        ) from exc

    metric = data.get("metric")
    conditions = data.get("conditions")
    if not metric or not isinstance(conditions, dict) or not conditions:
        raise RuntimeError(
            f"\n[SERA Runner] {METRICS_PREFIX} payload must have 'metric' and a "
            f"non-empty 'conditions' object. Got: {payload[:200]}\nRun log: {log_path}"
        )
    return metric, conditions


def _write_run_log(client, experiment_id, cmd, exit_code, stdout, stderr) -> Path:
    """Write a run log file under logs_root/<client>/ and return its path."""
    logs_dir = PROJECT_ROOT / CONFIG["paths"]["logs_root"] / client
    ensure_dir(logs_dir)

    n = len(list(logs_dir.glob(f"run-{experiment_id}-*.log"))) + 1
    log_path = logs_dir / f"run-{experiment_id}-{n:03d}.log"

    log_path.write_text(
        (
            f"command: {' '.join(cmd)}\n"
            f"exit_code: {exit_code}\n"
            "\n--- stdout ---\n"
            f"{stdout}\n"
            "\n--- stderr ---\n"
            f"{stderr}\n"
        ),
        encoding="utf-8",
    )
    return log_path

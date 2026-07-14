"""
engine/scriptgen.py — Claude-generated experiment scripts for SERA.

Public API:
    generate_script(client, experiment_id, max_repair_attempts=2) -> dict
        Reads the experiment, its hypothesis, and the source brief, asks
        Claude to write a standalone stdlib-only experiment script, validates
        the code, attaches it via engine.runner.attach_script, and executes it
        via engine.runner.run. Validation or run failures are fed back to
        Claude for repair, up to max_repair_attempts times.

        Returns the runner.run() summary dict plus:
            "attempts": total Claude calls made (1 = first try worked)
            "mode":     "simulation" or "measurement" (from the script's
                        honest MODE: simulation self-labeling)

    validate_script(code) -> list[str]
        Static checks on generated code. Returns a list of violations
        (empty = valid): parses cleanly, imports only from ALLOWED_IMPORTS,
        never calls open/exec/eval/__import__/compile, and contains the
        literal SERA_METRICS output contract.

Requires ANTHROPIC_API_KEY. There is deliberately NO offline fallback here:
a canned script pretending to be generated would poison experiment results.
"""

import ast
import json
import os
import tempfile

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown

DEFAULT_MODEL = "claude-sonnet-4-6"

ALLOWED_IMPORTS = {
    "json", "math", "re", "random", "string", "statistics", "collections",
    "itertools", "functools", "heapq", "bisect", "difflib", "textwrap",
    "datetime", "time", "typing", "dataclasses", "sys",
}

FORBIDDEN_CALLS = {"open", "exec", "eval", "__import__", "compile"}

SIMULATION_MARKER = "MODE: simulation"

SYSTEM_PROMPT = (
    "You are an experiment engineer. You write COMPLETE standalone Python "
    "experiment scripts that test a research hypothesis empirically.\n\n"
    "Hard requirements — every one is mandatory:\n"
    "1. Use ONLY the Python standard library, and only these modules: "
    + ", ".join(sorted(ALLOWED_IMPORTS)) + ".\n"
    "2. Be fully deterministic: seed any randomness with a fixed seed "
    "(e.g. random.seed(42)).\n"
    "3. Define at least 2 experimental conditions derived from the "
    "hypothesis, and evaluate all conditions on the same data.\n"
    "4. Finish in under 60 seconds.\n"
    "5. NO network access and NO file I/O of any kind: never call open(), "
    "exec(), eval(), __import__(), or compile().\n"
    "6. Print per-condition results as you go, then as the FINAL stdout "
    "line print EXACTLY this contract (no colon after SERA_METRICS):\n"
    '   SERA_METRICS {"metric": "<metric_name>", "conditions": '
    '{"<condition_label>": <numeric_value>, ...}}\n'
    "   The metric MUST be higher-is-better. Never negate a lower-is-better "
    "metric to fake this (metric names starting with 'neg_' are rejected): "
    "transform it into a genuinely higher-is-better quantity instead (e.g. "
    "wait time -> rate = successes / total_wait_seconds) and name the "
    "metric for what it now measures.\n"
    "7. Be honest about what you measure: if the script simulates behavior "
    "rather than measuring a real system, its FIRST output line must be "
    f"exactly '{SIMULATION_MARKER}'.\n\n"
    "8. Keep the script compact — under 150 lines. Use only ASCII characters "
    "in the source (no em-dashes or typographic quotes).\n\n"
    "Return ONLY the Python source code. No markdown fences, no commentary."
)


def generate_script(
    client: str,
    experiment_id: str,
    max_repair_attempts: int = 2,
    and_run: bool = True,
    timeout: int = 300,
) -> dict:
    """
    Generate, validate, attach, and execute an experiment script via Claude.

    Args:
        client:              Client slug (e.g. "acme-corp").
        experiment_id:       Experiment to generate for (e.g. "exp-001").
        max_repair_attempts: Repair rounds allowed after the initial attempt.
        and_run:             If False, stop after validate + attach (no run).
        timeout:             Max seconds each script execution may take.

    Returns:
        engine.runner.run() summary dict plus {"attempts": n, "mode": ...}.
        With and_run=False: {"attempts", "mode", "script_path"}.

    Raises:
        RuntimeError:      If ANTHROPIC_API_KEY is missing, or all attempts
                           are exhausted (message includes the attempt log).
        FileNotFoundError: If the experiment/hypothesis/brief files are missing.
    """
    from engine.runner import attach_script, run  # local import to avoid circular

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "\n[SERA ScriptGen] ANTHROPIC_API_KEY is not set.\n"
            "Script generation calls Claude and has no offline fallback -- a "
            "canned script pretending to be generated would poison results.\n"
            "Set the key and retry:  $env:ANTHROPIC_API_KEY = 'sk-ant-...'"
        )

    context = _load_context(client, experiment_id)
    log_lines = [f"scriptgen attempt log — client={client} experiment={experiment_id}"]
    log_path = _attempt_log_path(client, experiment_id)

    messages = [{"role": "user", "content": _build_user_prompt(context)}]
    attempts = 0

    while True:
        attempts += 1
        log_lines.append(f"\n===== attempt {attempts} =====")
        code = _extract_code(_call_claude(SYSTEM_PROMPT, messages))
        log_lines.append(code)

        violations = validate_script(code)
        if violations:
            log_lines.append(f"-- validation violations: {violations}")
            failure = "Static validation failed:\n" + "\n".join(f"- {v}" for v in violations)
        else:
            script_path = _write_temp_script(code, experiment_id)
            try:
                attached = attach_script(client, experiment_id, script_path)
            finally:
                os.unlink(script_path)

            if not and_run:
                _write_attempt_log(log_path, log_lines + ["-- attached without run"])
                return {
                    "attempts": attempts,
                    "mode": "simulation" if SIMULATION_MARKER in code else "measurement",
                    "script_path": attached,
                }

            try:
                summary = run(client, experiment_id, timeout=timeout)
                _write_attempt_log(log_path, log_lines + ["-- run succeeded"])
                summary["attempts"] = attempts
                summary["mode"] = _detect_mode(summary["log_path"])
                return summary
            except Exception as exc:  # noqa: BLE001 — anything goes back to Claude
                failure = f"The script failed at runtime:\n{exc}\n{_read_run_stderr(client, experiment_id)}"
                log_lines.append(f"-- run failed: {exc}")

        if attempts > max_repair_attempts:
            _write_attempt_log(log_path, log_lines + ["-- attempts exhausted"])
            raise RuntimeError(
                f"\n[SERA ScriptGen] Could not produce a working script for "
                f"'{experiment_id}' after {attempts} attempts "
                f"({max_repair_attempts} repairs).\nFull attempt log: {log_path}"
            )

        messages.append({"role": "assistant", "content": code})
        messages.append({
            "role": "user",
            "content": (
                f"{failure}\n\n"
                "Return the FULL corrected script. Same hard requirements as "
                "before: only the Python source code, no markdown fences."
            ),
        })


def validate_script(code: str) -> list:
    """
    Statically validate generated experiment code. Returns violations
    (empty list = valid).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: line {exc.lineno}: {exc.msg}"]

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    violations.append(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORTS:
                violations.append(f"forbidden import: from {node.module or '.'}")
        elif isinstance(node, ast.Call):
            # Only bare-name calls: the builtins open()/exec()/eval()/etc.
            # Attribute calls like re.compile() are legitimate — the import
            # allowlist already blocks modules that could smuggle file or
            # process access (os, builtins, subprocess are not allowed).
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                violations.append(f"forbidden call: {node.func.id}()")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value.startswith("neg_"):
            violations.append(
                f"negated metric name '{node.value}': metrics must be genuinely "
                "higher-is-better — transform lower-is-better quantities (e.g. "
                "rate = successes / total_wait) instead of negating them"
            )

    if "SERA_METRICS" not in code:
        violations.append(
            "missing the literal SERA_METRICS output contract "
            '(final line must be: SERA_METRICS {"metric": ..., "conditions": ...})'
        )
    return violations


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_claude(system: str, messages: list) -> str:
    """
    One Claude call. Kept small so tests can mock the Anthropic client.

    Runs under engine.api.call_with_backoff: 429s are retried with backoff,
    and a credit-exhaustion error is raised as BillingError so it aborts the
    whole run rather than being logged as a repairable script failure.
    """
    import anthropic as _anthropic  # optional import — not in requirements.txt

    from engine.api import call_with_backoff

    model = CONFIG.get("llm", {}).get("model", DEFAULT_MODEL)
    ai = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = call_with_backoff(lambda: ai.messages.create(
        model=model,
        max_tokens=8000,
        system=system,
        messages=messages,
    ))
    return msg.content[0].text


def _load_context(client: str, experiment_id: str) -> dict:
    """Read the experiment, its hypothesis, and the source brief."""
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    client_root = clients_root / client

    exp_fm, exp_body = read_markdown(client_root / "experiments" / f"{experiment_id}.md")

    hyp_id = exp_fm.get("hypothesis_id", "")
    hyp_fm, hyp_body = read_markdown(client_root / "hypotheses" / f"{hyp_id}.md")

    brief_id = hyp_fm.get("brief_id", "")
    brief_fm, brief_body = read_markdown(client_root / "briefs" / f"{brief_id}.md")

    return {
        "experiment": (exp_fm, exp_body),
        "hypothesis": (hyp_fm, hyp_body),
        "brief": (brief_fm, brief_body),
    }


def _build_user_prompt(context: dict) -> str:
    brief_fm, brief_body = context["brief"]
    hyp_fm, hyp_body = context["hypothesis"]
    exp_fm, exp_body = context["experiment"]

    predicted = hyp_fm.get("predicted_winner", "")
    prediction_section = (
        f"## Prediction contract\nThe hypothesis predicts the winning condition "
        f"will be '{predicted}'. One of your condition labels MUST be exactly "
        f"'{predicted}', verbatim, so the prediction can be scored against the "
        "outcome. Name the competing conditions in the same style.\n\n"
        if predicted else ""
    )

    return (
        "Write the experiment script for this research context.\n\n"
        f"## Research brief: {brief_fm.get('title', '')}\n{brief_body}\n\n"
        f"## Hypothesis: {hyp_fm.get('title', '')}\n{hyp_body}\n\n"
        f"{prediction_section}"
        f"## Experiment design: {exp_fm.get('title', '')}\n{exp_body}\n"
    )


def _extract_code(text: str) -> str:
    """Strip accidental markdown code fences from a Claude response."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("python"):
                text = text[len("python"):]
    return text.strip()


def _write_temp_script(code: str, experiment_id: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".py", prefix=f"sera-{experiment_id}-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(code)
    return path


def _attempt_log_path(client: str, experiment_id: str):
    logs_dir = PROJECT_ROOT / CONFIG["paths"]["logs_root"] / client
    ensure_dir(logs_dir)
    n = len(list(logs_dir.glob(f"scriptgen-{experiment_id}-*.log"))) + 1
    return logs_dir / f"scriptgen-{experiment_id}-{n:03d}.log"


def _write_attempt_log(log_path, log_lines: list) -> None:
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def _read_run_stderr(client: str, experiment_id: str) -> str:
    """Pull the stderr section from the most recent run log, for repair context."""
    logs_dir = PROJECT_ROOT / CONFIG["paths"]["logs_root"] / client
    logs = sorted(logs_dir.glob(f"run-{experiment_id}-*.log"))
    if not logs:
        return ""
    text = logs[-1].read_text(encoding="utf-8")
    marker = "--- stderr ---"
    return text[text.index(marker):] if marker in text else ""


def _detect_mode(run_log_path) -> str:
    """Read the honest MODE self-label from the run's captured stdout."""
    try:
        text = run_log_path.read_text(encoding="utf-8")
    except OSError:
        return "measurement"
    return "simulation" if SIMULATION_MARKER in text else "measurement"

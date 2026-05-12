"""
engine/winner.py — Winner selection for SERA experiments.

Public API:
    select_winner(client, experiment_id) -> dict
        Compares all logged result values for an experiment, marks the
        highest-value result as winner, updates confidence scores for all
        results, and sets the experiment status to "complete".

        Returns a summary dict with the winner's details.
"""

from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import read_markdown, write_markdown


def select_winner(client: str, experiment_id: str) -> dict:
    """
    Select the winning result for a completed experiment.

    Compares the numeric "value" field across all results for the experiment.
    The result with the highest value is marked as winner. Confidence scores
    are computed relative to the observed value range.

    Args:
        client:        Client slug (e.g. "acme-corp").
        experiment_id: Experiment to evaluate (e.g. "exp-001").

    Returns:
        Dict with keys: winner_id, winner_condition, winner_metric,
        winner_value, experiment_id, total_results.

    Raises:
        ValueError: If no results exist for the experiment.
    """
    from engine.results import list_results  # local import to avoid circular

    results = list_results(client, experiment_id)
    if not results:
        raise ValueError(
            f"[SERA Engine] No results found for experiment '{experiment_id}' "
            f"of client '{client}'. Log results first with engine.results.log_result()."
        )

    values = [_parse_value(r) for r in results]
    max_val = max(values)
    min_val = min(values)
    value_range = max_val - min_val

    winner_idx = values.index(max_val)
    winner_result = results[winner_idx]

    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    results_dir = clients_root / client / "results"

    for result, val in zip(results, values):
        is_winner = result is winner_result
        confidence = (
            (val - min_val) / value_range if value_range > 0.0 else 0.5
        )
        _update_result(results_dir, result, is_winner=is_winner, confidence=confidence)

    _mark_experiment_complete(clients_root / client / "experiments" / f"{experiment_id}.md")

    return {
        "winner_id": winner_result["id"],
        "winner_condition": winner_result.get("condition", ""),
        "winner_metric": winner_result.get("metric", ""),
        "winner_value": max_val,
        "experiment_id": experiment_id,
        "total_results": len(results),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_value(result: dict) -> float:
    """Extract and coerce the numeric value from a result dict."""
    try:
        return float(result.get("value", 0))
    except (TypeError, ValueError):
        return 0.0


def _update_result(results_dir: Path, result: dict, is_winner: bool, confidence: float) -> None:
    """Rewrite a result file with updated winner flag, confidence, and status."""
    result_path = results_dir / f"{result['id']}.md"
    _, existing_body = read_markdown(result_path)

    winner_str = "true" if is_winner else "false"
    confidence_pct = round(confidence * 100, 1)

    new_fm = {
        "id": result["id"],
        "experiment_id": result["experiment_id"],
        "client_id": result["client_id"],
        "condition": result.get("condition", ""),
        "metric": result.get("metric", ""),
        "value": result.get("value", 0),
        "winner": winner_str,
        "confidence": round(confidence, 2),
        "status": "final",
        "recorded_on": result.get("recorded_on", ""),
    }

    winner_line = (
        "**Winner:** Yes -- this result is recommended for promotion."
        if is_winner
        else "**Winner:** No -- this result did not meet the winning threshold."
    )

    outcome = result.get("outcome", f"Result: {result['id']}")
    data_summary = result.get(
        "data_summary",
        f"| Condition | Metric | Value |\n|-----------|--------|-------|\n"
        f"| {result.get('condition', '')} | {result.get('metric', '')} | {result.get('value', '')} |",
    )
    notes = result.get("notes", "_No additional notes._")

    body = (
        f"# Result: {result['id']}\n\n"
        "## Outcome\n\n"
        f"{outcome}\n\n"
        "## Data Summary\n\n"
        f"{data_summary}\n\n"
        "## Winner Determination\n\n"
        f"{winner_line}\n\n"
        f"**Confidence Score:** {confidence_pct}%\n\n"
        "## Analyst Notes\n\n"
        f"{notes}\n\n"
        "---\n\n"
        f"**Status:** `final`\n"
        f"**Experiment:** [[experiments/{result['experiment_id']}]]\n"
        f"**Client:** [[clients/{result['client_id']}/_meta]]"
    )

    write_markdown(result_path, body, new_fm)


def _mark_experiment_complete(exp_path: Path) -> None:
    """Update experiment status to 'complete' if the file exists."""
    if not exp_path.exists():
        return
    fm, body = read_markdown(exp_path)
    fm["status"] = "complete"
    write_markdown(exp_path, body, fm)

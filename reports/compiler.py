"""
reports/compiler.py — Gather all vault data needed for a research report.

Public API:
    compile_report_data(client, brief_id) -> dict
        Reads brief, hypotheses, experiments, and results from the vault
        filesystem and returns a unified dict for the formatter.
"""

from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import read_markdown


def compile_report_data(client: str, brief_id: str) -> dict:
    """
    Walk the vault and collect all data for a research report.

    Args:
        client:   Client slug (e.g. "acme-corp").
        brief_id: Brief file ID (e.g. "brief-001"), without .md extension.

    Returns:
        Dict with keys: client, brief_id, brief, hypotheses, experiments,
        all_results, winners.

    Raises:
        FileNotFoundError: If the brief file does not exist.
    """
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    client_dir = clients_root / client

    brief = _read_brief(client_dir, brief_id)
    hypotheses = _read_hypotheses(client_dir, brief_id)

    all_experiments = []
    all_results = []
    all_winners = []

    for hyp in hypotheses:
        experiments = _read_experiments(client_dir, hyp["id"])
        for exp in experiments:
            results = _read_results(client_dir, exp["id"])
            exp["results"] = results
            exp["results_count"] = len(results)
            all_results.extend(results)

            winner = _find_winner(results, exp)
            exp["winner"] = winner
            if winner:
                all_winners.append(winner)

        hyp["experiments"] = experiments
        all_experiments.extend(experiments)

    return {
        "client": client,
        "brief_id": brief_id,
        "brief": brief,
        "hypotheses": hypotheses,
        "experiments": all_experiments,
        "all_results": all_results,
        "winners": all_winners,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_brief(client_dir: Path, brief_id: str) -> dict:
    brief_path = client_dir / "briefs" / f"{brief_id}.md"
    fm, body = read_markdown(brief_path)
    return {"frontmatter": fm, "body": body}


def _read_hypotheses(client_dir: Path, brief_id: str) -> list:
    hyp_dir = client_dir / "hypotheses"
    if not hyp_dir.exists():
        return []

    collected = []
    for md_path in sorted(hyp_dir.glob("hyp-*.md")):
        fm, body = read_markdown(md_path)
        if fm.get("brief_id") != brief_id:
            continue
        collected.append({
            "id": fm.get("id", md_path.stem),
            "title": fm.get("title", md_path.stem),
            "hypothesis": _extract_hypothesis_text(body),
            "status": fm.get("status", "draft"),
            "brief_id": fm.get("brief_id", brief_id),
            "created": fm.get("created", ""),
            "outcome": _status_to_outcome(fm.get("status", "draft")),
        })
    return collected


def _read_experiments(client_dir: Path, hypothesis_id: str) -> list:
    exp_dir = client_dir / "experiments"
    if not exp_dir.exists():
        return []

    collected = []
    for md_path in sorted(exp_dir.glob("exp-*.md")):
        fm, _ = read_markdown(md_path)
        if fm.get("hypothesis_id") != hypothesis_id:
            continue
        collected.append({
            "id": fm.get("id", md_path.stem),
            "title": fm.get("title", md_path.stem),
            "hypothesis_id": fm.get("hypothesis_id", hypothesis_id),
            "methodology": fm.get("methodology", "A/B test"),
            "status": fm.get("status", "pending"),
            "created": fm.get("created", ""),
        })
    return collected


def _read_results(client_dir: Path, experiment_id: str) -> list:
    res_dir = client_dir / "results"
    if not res_dir.exists():
        return []

    collected = []
    for md_path in sorted(res_dir.glob("res-*.md")):
        fm, _ = read_markdown(md_path)
        if fm.get("experiment_id") != experiment_id:
            continue
        is_winner = str(fm.get("winner", "false")).lower() == "true"
        try:
            confidence = float(fm.get("confidence", 0))
        except (ValueError, TypeError):
            confidence = 0.0
        try:
            value = float(fm.get("value", 0))
        except (ValueError, TypeError):
            value = 0.0
        collected.append({
            "id": fm.get("id", md_path.stem),
            "experiment_id": fm.get("experiment_id", experiment_id),
            "condition": fm.get("condition", ""),
            "metric": fm.get("metric", ""),
            "value": value,
            "winner": is_winner,
            "confidence": confidence,
            "status": fm.get("status", "draft"),
            "recorded_on": fm.get("recorded_on", ""),
        })
    return collected


def _find_winner(results: list, experiment: dict) -> dict | None:
    """
    Identify the winning result for an experiment.

    Prefers the explicit winner flag written by engine.winner.select_winner.
    If no result is flagged, picks the highest-value result as a provisional lead.
    """
    if not results:
        return None

    for r in results:
        if r["winner"]:
            return _winner_summary(r, experiment, finalized=True)

    best = max(results, key=lambda r: r["value"])
    return _winner_summary(best, experiment, finalized=False)


def _winner_summary(result: dict, experiment: dict, finalized: bool) -> dict:
    label = "wins" if finalized else "leads (provisional)"
    outcome_suffix = "" if finalized else " (experiment not yet finalized)"
    return {
        "title": f"{experiment['title']} — Condition {result['condition']} {label}",
        "confidence": result["confidence"],
        "outcome": (
            f"Condition {result['condition']} achieved the highest "
            f"{result['metric']} at {result['value']}"
            f" with {round(result['confidence'] * 100, 1)}% confidence{outcome_suffix}."
        ),
        "experiment_id": experiment["id"],
        "result_id": result["id"],
        "metric": result["metric"],
        "value": result["value"],
    }


def _extract_hypothesis_text(body: str) -> str:
    """Pull the 'If X, then Y' statement out of a hypothesis body."""
    for line in body.splitlines():
        stripped = line.strip()
        # Written by engine.hypothesis as: "> **<text>**"
        if stripped.startswith("> **") and stripped.endswith("**"):
            return stripped[4:-2].strip()
        if stripped.startswith("> ") and stripped[2:].strip():
            return stripped[2:].strip()
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def _status_to_outcome(status: str) -> str:
    return {
        "draft": "Under review",
        "active": "Currently being tested",
        "complete": "Testing complete",
        "archived": "Archived — no longer active",
    }.get(status, status.capitalize())

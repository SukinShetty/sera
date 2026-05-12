"""
engine/results.py — Result logging and listing for SERA experiments.

Public API:
    log_result(client, experiment_id, condition, metric, value, notes="") -> str
        Records one result measurement for an experiment condition.
        Returns the result ID.

    list_results(client, experiment_id) -> list[dict]
        Returns all logged results for a given experiment as a list of dicts
        (each dict is the parsed frontmatter plus a "path" key).
"""

from datetime import date
from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown


def log_result(
    client: str,
    experiment_id: str,
    condition: str,
    metric: str,
    value: float,
    notes: str = "",
) -> str:
    """
    Log a measurement result for one condition of an experiment.

    Each call creates one result Markdown file. Multiple conditions (e.g. A, B)
    are stored as separate files and compared by select_winner.

    Args:
        client:        Client slug (e.g. "acme-corp").
        experiment_id: Experiment being measured (e.g. "exp-001").
        condition:     Label for the condition measured (e.g. "A", "B", "control").
        metric:        The metric being measured (e.g. "conversion_rate").
        value:         The measured numeric value (e.g. 0.35).
        notes:         Optional analyst notes.

    Returns:
        The result ID (e.g. "res-exp-001-a").
    """
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    results_dir = clients_root / client / "results"
    ensure_dir(results_dir)

    res_id = _unique_result_id(results_dir, experiment_id, condition)

    res_data = {
        "id": res_id,
        "experiment_id": experiment_id,
        "client_id": client,
        "condition": condition,
        "metric": metric,
        "value": float(value),
        "outcome": f"Condition {condition}: {metric} measured at {value}",
        "data_summary": (
            f"| Condition | Metric | Value |\n"
            f"|-----------|--------|-------|\n"
            f"| {condition} | {metric} | {value} |"
        ),
        "winner": False,
        "confidence": 0.0,
        "notes": notes if notes else "_No additional notes._",
        "status": "draft",
        "recorded_on": date.today().isoformat(),
    }

    _write_result(results_dir / f"{res_id}.md", res_data)
    return res_id


def list_results(client: str, experiment_id: str) -> list[dict]:
    """
    Return all logged results for a given experiment.

    Args:
        client:        Client slug.
        experiment_id: Experiment to filter by.

    Returns:
        List of dicts — each has all frontmatter fields plus "path" (Path object).
        Sorted by result ID ascending. Empty list if none found.
    """
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    results_dir = clients_root / client / "results"
    if not results_dir.exists():
        return []

    matches = []
    for md_path in sorted(results_dir.glob("*.md")):
        fm, _ = read_markdown(md_path)
        if fm.get("experiment_id") == experiment_id:
            matches.append({"path": md_path, **fm})

    return matches


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _unique_result_id(results_dir: Path, experiment_id: str, condition: str) -> str:
    """Build a unique result ID, adding a sequence suffix if needed."""
    slug = condition.lower().replace(" ", "-")
    base = f"res-{experiment_id}-{slug}"
    if not (results_dir / f"{base}.md").exists():
        return base
    # Add a numeric suffix to avoid collision
    n = 2
    while (results_dir / f"{base}-{n:02d}.md").exists():
        n += 1
    return f"{base}-{n:02d}"


def _write_result(path: Path, data: dict) -> None:
    """Write a result markdown file matching vault/templates/result.md format."""
    winner_str = "true" if data["winner"] else "false"

    frontmatter = {
        "id": data["id"],
        "experiment_id": data["experiment_id"],
        "client_id": data["client_id"],
        "condition": data["condition"],
        "metric": data["metric"],
        "value": data["value"],
        "winner": winner_str,
        "confidence": data["confidence"],
        "status": data["status"],
        "recorded_on": data["recorded_on"],
    }

    winner_line = (
        "**Winner:** Yes -- this result is recommended for promotion."
        if data["winner"]
        else "**Winner:** No -- this result did not meet the winning threshold."
    )
    confidence_pct = round(data["confidence"] * 100, 1)

    body = (
        f"# Result: {data['id']}\n\n"
        "## Outcome\n\n"
        f"{data['outcome']}\n\n"
        "## Data Summary\n\n"
        f"{data['data_summary']}\n\n"
        "## Winner Determination\n\n"
        f"{winner_line}\n\n"
        f"**Confidence Score:** {confidence_pct}%\n\n"
        "## Analyst Notes\n\n"
        f"{data['notes']}\n\n"
        "---\n\n"
        f"**Status:** `{data['status']}`\n"
        f"**Experiment:** [[experiments/{data['experiment_id']}]]\n"
        f"**Client:** [[clients/{data['client_id']}/_meta]]"
    )

    write_markdown(path, body, frontmatter)

"""
engine/experiment.py — Experiment creation for SERA.

Public API:
    create(client, hypothesis_id) -> str
        Reads the hypothesis, scaffolds an experiment Markdown file in the
        client's experiments/ folder, and returns the new experiment ID.
"""

from datetime import date
from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown


def create(client: str, hypothesis_id: str) -> str:
    """
    Create an experiment from an existing hypothesis.

    Args:
        client:        Client slug (e.g. "acme-corp").
        hypothesis_id: Hypothesis ID to test (e.g. "hyp-001"), without .md.

    Returns:
        The new experiment ID (e.g. "exp-001").

    Raises:
        FileNotFoundError: If the hypothesis file does not exist.
    """
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    hyp_path = clients_root / client / "hypotheses" / f"{hypothesis_id}.md"
    fm, _ = read_markdown(hyp_path)

    exp_dir = clients_root / client / "experiments"
    ensure_dir(exp_dir)

    existing = sorted(exp_dir.glob("exp-*.md"))
    exp_id = f"exp-{len(existing) + 1:03d}"

    hyp_title = fm.get("title", hypothesis_id)

    exp_data = {
        "id": exp_id,
        "hypothesis_id": hypothesis_id,
        "client_id": client,
        "title": f"Test: {hyp_title}",
        "methodology": "A/B test",
        "independent_variable": "Treatment condition (A vs B)",
        "dependent_variable": hyp_title,
        "control_variable": "All other factors held constant",
        "expected_outcome": (
            f"Condition B will outperform Condition A on the metrics defined in hypothesis {hypothesis_id}."
        ),
        "status": "pending",
        "created": date.today().isoformat(),
    }

    _write_experiment(exp_dir / f"{exp_id}.md", exp_data)
    return exp_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_experiment(path: Path, data: dict) -> None:
    """Write an experiment markdown file matching vault/templates/experiment.md format."""
    frontmatter = {
        "id": data["id"],
        "hypothesis_id": data["hypothesis_id"],
        "client_id": data["client_id"],
        "title": data["title"],
        "methodology": data["methodology"],
        "status": data["status"],
        "created": data["created"],
    }

    body = (
        f"# Experiment: {data['title']}\n\n"
        "## Methodology\n\n"
        f"{data['methodology']}\n\n"
        "## Variables\n\n"
        "| Role | Variable |\n"
        "|------|----------|\n"
        f"| **Independent** | {data['independent_variable']} |\n"
        f"| **Dependent** | {data['dependent_variable']} |\n"
        f"| **Control** | {data['control_variable']} |\n\n"
        "## Expected Outcome\n\n"
        f"{data['expected_outcome']}\n\n"
        "## Notes\n\n"
        "_Add experiment notes here._\n\n"
        "---\n\n"
        f"**Status:** `{data['status']}`\n"
        f"**Hypothesis:** [[hypotheses/{data['hypothesis_id']}]]\n"
        f"**Client:** [[clients/{data['client_id']}/_meta]]"
    )

    write_markdown(path, body, frontmatter)

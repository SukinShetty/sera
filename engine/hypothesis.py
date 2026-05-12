"""
engine/hypothesis.py — Research hypothesis generator for SERA.

Public API:
    generate(client, brief_id) -> list[str]
        Reads the client's research brief, generates 3 practical hypotheses,
        and writes each as a Markdown file in the client's hypotheses/ folder.
        Returns the list of created hypothesis IDs.

Anthropic API is used when ANTHROPIC_API_KEY is set; otherwise a structured
fallback generator produces 3 hypothesis files so the MVP always works.
"""

import json
import os
from datetime import date
from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown


def generate(client: str, brief_id: str) -> list[str]:
    """
    Generate 3 research hypotheses from an existing brief.

    Args:
        client:   Client slug (e.g. "acme-corp"). Must have a vault already.
        brief_id: ID of the brief file (e.g. "brief-001"), without .md extension.

    Returns:
        List of hypothesis IDs created (e.g. ["hyp-001", "hyp-002", "hyp-003"]).

    Raises:
        FileNotFoundError: If the brief file does not exist.
    """
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    brief_path = clients_root / client / "briefs" / f"{brief_id}.md"
    fm, body = read_markdown(brief_path)

    hyp_dir = clients_root / client / "hypotheses"
    ensure_dir(hyp_dir)

    existing = sorted(hyp_dir.glob("hyp-*.md"))
    start_n = len(existing) + 1

    hypotheses = _generate_hypotheses(client, brief_id, fm, body)

    created_ids = []
    for i, hyp_data in enumerate(hypotheses, start=start_n):
        hyp_id = f"hyp-{i:03d}"
        hyp_data.update(
            id=hyp_id,
            brief_id=brief_id,
            client_id=client,
            status="draft",
            created=date.today().isoformat(),
        )
        _write_hypothesis(hyp_dir / f"{hyp_id}.md", hyp_data)
        created_ids.append(hyp_id)

    return created_ids


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_hypotheses(client: str, brief_id: str, brief_fm: dict, brief_body: str) -> list[dict]:
    """Try Anthropic API first; fall back to templated generation."""
    try:
        return _generate_via_anthropic(client, brief_id, brief_fm, brief_body)
    except Exception:
        return _generate_fallback(brief_fm, brief_body)


def _generate_via_anthropic(client: str, brief_id: str, brief_fm: dict, brief_body: str) -> list[dict]:
    import anthropic as _anthropic  # optional import — not in requirements.txt

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    brief_title = brief_fm.get("title", "Research Brief")
    objective = brief_body[:1200] if brief_body else brief_title

    prompt = (
        "You are a research strategist. Generate exactly 3 testable research hypotheses "
        f"for this brief.\n\nClient: {client}\nBrief ID: {brief_id}\n"
        f"Brief title: {brief_title}\n\nBrief content:\n{objective}\n\n"
        "Return ONLY a JSON array with exactly 3 objects. Each object must have:\n"
        '  "title": short label (5-8 words)\n'
        '  "hypothesis": "If X, then Y, because Z" statement\n'
        '  "rationale": 1-2 sentences of supporting reasoning\n'
        '  "metrics": array of 2-3 measurable success metrics (strings)\n'
        "No markdown fences, no explanation — raw JSON only."
    )

    ai = _anthropic.Anthropic(api_key=api_key)
    msg = ai.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    # Strip accidental markdown code fences
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) >= 2 else raw

    data = json.loads(raw)
    if not isinstance(data, list) or len(data) < 3:
        raise ValueError(f"Unexpected API response shape: {raw[:200]}")
    return data[:3]


def _generate_fallback(brief_fm: dict, brief_body: str) -> list[dict]:
    """Template-based hypotheses derived from the brief. Always works offline."""
    label = brief_fm.get("title", "the research objective")
    short = label[:50]

    return [
        {
            "title": f"Audience Alignment: {short}",
            "hypothesis": (
                f"If we align our offering more precisely with the target audience's core needs, "
                f"then engagement with {label} will increase, "
                "because reducing friction in the value proposition converts more prospects."
            ),
            "rationale": (
                "Audience-offering fit is the strongest early-stage growth driver. "
                "A clearer value proposition reduces drop-off at the first touchpoint."
            ),
            "metrics": [
                "Engagement rate increase >= 15%",
                "Bounce rate decrease >= 10%",
                "Conversion rate uplift >= 5%",
            ],
        },
        {
            "title": f"Channel Focus: {short}",
            "hypothesis": (
                "If we concentrate marketing spend on the highest-performing acquisition channel, "
                f"then cost-per-acquisition for {label} will decrease, "
                "because focused spend outperforms diluted multi-channel approaches at this scale."
            ),
            "rationale": (
                "Early-stage businesses typically see 80% of results from 20% of channels. "
                "Doubling down on the top channel amplifies returns before diversifying."
            ),
            "metrics": [
                "Cost-per-acquisition reduction >= 20%",
                "Channel ROI increase >= 30%",
                "Lead quality score improvement",
            ],
        },
        {
            "title": f"Early Retention Driver: {short}",
            "hypothesis": (
                "If we address the primary churn trigger within the first 30 days, "
                f"then retention for {label} will improve, "
                "because early activation is the strongest predictor of long-term retention."
            ),
            "rationale": (
                "Users who hit activation milestones early have 3-5x higher lifetime value. "
                "Reducing early-stage churn compounds growth over every subsequent cohort."
            ),
            "metrics": [
                "30-day retention rate increase >= 10%",
                "Activation rate improvement >= 15%",
                "NPS uplift >= 8 points",
            ],
        },
    ]


def _write_hypothesis(path: Path, data: dict) -> None:
    """Write a hypothesis markdown file matching vault/templates/hypothesis.md format."""
    metrics_lines = "\n".join(f"- {m}" for m in data.get("metrics", []))
    metrics_section = metrics_lines or "_No success metrics defined yet._"

    frontmatter = {
        "id": data["id"],
        "brief_id": data["brief_id"],
        "client_id": data["client_id"],
        "title": data["title"],
        "status": data["status"],
        "created": data["created"],
    }

    body = (
        f"# Hypothesis: {data['title']}\n\n"
        f"> **{data['hypothesis']}**\n\n"
        "## Rationale\n\n"
        f"{data.get('rationale', '_No rationale provided._')}\n\n"
        "## Success Metrics\n\n"
        f"{metrics_section}\n\n"
        "---\n\n"
        f"**Status:** `{data['status']}`\n"
        f"**Brief:** [[briefs/{data['brief_id']}]]\n"
        f"**Client:** [[clients/{data['client_id']}/_meta]]"
    )

    write_markdown(path, body, frontmatter)

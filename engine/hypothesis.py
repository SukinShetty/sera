"""
engine/hypothesis.py — Research hypothesis generator for SERA.

Public API:
    generate(client, brief_id, memory=True) -> list[str]
        Reads the client's research brief, generates 3 practical hypotheses,
        and writes each as a Markdown file in the client's hypotheses/ folder.
        Returns the list of created hypothesis IDs.

        Every hypothesis carries a `predicted_winner` frontmatter field: the
        condition label it expects to win. Downstream, scriptgen forces that
        label to appear verbatim among the experiment's conditions, and the
        outcome ledger scores the prediction (survived/killed).

        With memory=True (default), relevant past outcomes from
        engine.ledger are injected into the generation prompt so new
        hypotheses calibrate on what actually happened. The exact injected
        block (or "none") is written to engine/logs/<client>/hypgen-*.log
        so memory-on/off runs are auditable.

Anthropic API is used when ANTHROPIC_API_KEY is set; otherwise a structured
fallback generator produces 3 hypothesis files so the MVP always works.
"""

import json
import os
from datetime import date
from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown


def generate(client: str, brief_id: str, memory: bool = True) -> list[str]:
    """
    Generate 3 research hypotheses from an existing brief.

    Args:
        client:   Client slug (e.g. "acme-corp"). Must have a vault already.
        brief_id: ID of the brief file (e.g. "brief-001"), without .md extension.
        memory:   Inject relevant past outcomes from the ledger into the
                  generation prompt (the ablation lever — see module docstring).

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

    memory_block = _build_memory_block(fm, body) if memory else None
    _log_memory_block(client, brief_id, memory_block)

    hypotheses = _generate_hypotheses(client, brief_id, fm, body, memory_block)

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

def _generate_hypotheses(
    client: str, brief_id: str, brief_fm: dict, brief_body: str, memory_block: str = None
) -> list[dict]:
    """Try Anthropic API first; fall back to templated generation."""
    try:
        return _generate_via_anthropic(client, brief_id, brief_fm, brief_body, memory_block)
    except Exception:
        return _generate_fallback(brief_fm, brief_body)


def _generate_via_anthropic(
    client: str, brief_id: str, brief_fm: dict, brief_body: str, memory_block: str = None
) -> list[dict]:
    import anthropic as _anthropic  # optional import — not in requirements.txt

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    brief_title = brief_fm.get("title", "Research Brief")
    objective = brief_body[:1200] if brief_body else brief_title

    memory_section = f"{memory_block}\n\n" if memory_block else ""

    prompt = (
        "You are a research strategist. Generate exactly 3 testable research hypotheses "
        f"for this brief.\n\nClient: {client}\nBrief ID: {brief_id}\n"
        f"Brief title: {brief_title}\n\nBrief content:\n{objective}\n\n"
        f"{memory_section}"
        "Return ONLY a JSON array with exactly 3 objects. Each object must have:\n"
        '  "title": short label (5-8 words)\n'
        '  "hypothesis": "If X, then Y, because Z" statement\n'
        '  "rationale": 1-2 sentences of supporting reasoning\n'
        '  "metrics": array of 2-3 measurable success metrics (strings)\n'
        '  "predicted_winner": the condition label this hypothesis expects to win '
        '(short snake_case slug, e.g. "exponential_jitter")\n'
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
    if any(not item.get("predicted_winner") for item in data[:3]):
        raise ValueError("API response missing required 'predicted_winner' field")
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
            "predicted_winner": "aligned_offering",
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
            "predicted_winner": "focused_channel",
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
            "predicted_winner": "early_activation",
        },
    ]


def _build_memory_block(brief_fm: dict, brief_body: str) -> str:
    """
    Build the PAST RESEARCH OUTCOMES prompt block from the outcome ledger.
    Returns None when no relevant past outcomes exist.
    """
    from engine import ledger  # local import to avoid circular

    question = brief_fm.get("title") or brief_body[:200]
    entries = ledger.query(question)
    if not entries:
        return None

    lines = ["PAST RESEARCH OUTCOMES (from prior experiments — calibrate on these):"]
    for e in entries:
        lines.append(
            f"- Q: {e.get('question', '')} | predicted: {e.get('predicted_winner', '?')} "
            f"| actual winner: {e.get('actual_winner', '?')} | verdict: {e.get('verdict', '?')}"
        )
    return "\n".join(lines)


def _log_memory_block(client: str, brief_id: str, memory_block) -> None:
    """Write the exact injected memory block (or 'none') for auditability."""
    logs_dir = PROJECT_ROOT / CONFIG["paths"]["logs_root"] / client
    ensure_dir(logs_dir)
    n = len(list(logs_dir.glob(f"hypgen-{brief_id}-*.log"))) + 1
    (logs_dir / f"hypgen-{brief_id}-{n:03d}.log").write_text(
        "injected memory block:\n" + (memory_block if memory_block else "none") + "\n",
        encoding="utf-8",
    )


def _write_hypothesis(path: Path, data: dict) -> None:
    """Write a hypothesis markdown file matching vault/templates/hypothesis.md format."""
    metrics_lines = "\n".join(f"- {m}" for m in data.get("metrics", []))
    metrics_section = metrics_lines or "_No success metrics defined yet._"

    frontmatter = {
        "id": data["id"],
        "brief_id": data["brief_id"],
        "client_id": data["client_id"],
        "title": data["title"],
        "predicted_winner": data.get("predicted_winner", ""),
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

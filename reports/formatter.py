"""
reports/formatter.py — Render a compiled report dict into a Markdown document.

Public API:
    render_report(data) -> tuple[dict, str]
        Returns (frontmatter_dict, body_str) ready for write_markdown().

AI summary generation is attempted when ANTHROPIC_API_KEY is set.
Falls back to structured template-based text when unavailable.
"""

import os
from datetime import date

from jinja2 import Environment, BaseLoader


# ---------------------------------------------------------------------------
# Jinja2 body template — extends the vault/templates/report.md structure
# with the full set of required sections.
# ---------------------------------------------------------------------------

_REPORT_BODY_TEMPLATE = """\
# Research Report: {{ title }}

**Client:** {{ client_id }}
**Generated:** {{ generated_on }}

---

## Executive Summary

{{ executive_summary }}

---

## Client & Research Context

**Brief ID:** `{{ brief_id }}`
**Client:** {{ client_id }}

{{ research_context }}

---

## Hypotheses Tested

{% if hypotheses %}
{% for h in hypotheses %}
### {{ loop.index }}. {{ h.title }}

{% if h.hypothesis %}> {{ h.hypothesis }}

{% endif %}
**Status:** `{{ h.status }}`
**Outcome:** {{ h.outcome }}

{% endfor %}
{% else %}
_No hypotheses recorded._
{% endif %}

---

## Experiments Run

{% if experiments %}
| Experiment | Hypothesis | Methodology | Status | Results |
|------------|-----------|-------------|--------|---------|
{% for e in experiments %}
| `{{ e.id }}` | `{{ e.hypothesis_id }}` | {{ e.methodology }} | `{{ e.status }}` | {{ e.results_count }} |
{% endfor %}
{% else %}
_No experiments recorded._
{% endif %}

---

## Result Comparison

{% if all_results %}
| Result | Experiment | Condition | Metric | Value | Winner | Confidence |
|--------|-----------|-----------|--------|-------|--------|------------|
{% for r in all_results %}
| `{{ r.id }}` | `{{ r.experiment_id }}` | {{ r.condition }} | {{ r.metric }} | {{ r.value }} | {{ "Yes" if r.winner else "No" }} | {{ (r.confidence * 100) | round(1) }}% |
{% endfor %}
{% else %}
_No results recorded._
{% endif %}

---

## Winner Summary

{% if winners %}
{% for w in winners %}
### {{ loop.index }}. {{ w.title }}

**Confidence:** {{ (w.confidence * 100) | round(1) }}%

{{ w.outcome }}

{% endfor %}
{% else %}
_No winning experiments identified yet._
{% endif %}

---

## Recommendations

{% if recommendations %}
{% for rec in recommendations %}
{{ loop.index }}. {{ rec }}
{% endfor %}
{% else %}
_Recommendations to be added._
{% endif %}

---

## Next Experiments

{% if next_experiments %}
{% for nxt in next_experiments %}
{{ loop.index }}. {{ nxt }}
{% endfor %}
{% else %}
_Next experiments to be planned._
{% endif %}

---

## Appendix

_Raw experiment data and detailed result logs available in:_
- `[[clients/{{ client_id }}/experiments/]]`
- `[[clients/{{ client_id }}/results/]]`
- `[[clients/{{ client_id }}/hypotheses/]]`
"""


def render_report(data: dict) -> tuple:
    """
    Render a compiled report data dict into a Markdown document.

    Args:
        data: Dict returned by compiler.compile_report_data().

    Returns:
        (frontmatter_dict, body_str) for use with shared.file_io.write_markdown().
    """
    brief_fm = data["brief"]["frontmatter"]
    brief_body = data["brief"]["body"]
    client = data["client"]
    brief_id = data["brief_id"]
    today = date.today().isoformat()

    title = brief_fm.get("title", f"Research Report — {brief_id}")
    research_context = _build_research_context(brief_fm, brief_body)

    ai_output = _try_ai_generation(client, brief_id, title, data)
    executive_summary = ai_output.get("summary") or _build_fallback_summary(data, title)
    recommendations = ai_output.get("recommendations") or _build_fallback_recommendations(data)
    next_experiments = ai_output.get("next_experiments") or _build_fallback_next_experiments(data)

    frontmatter = {
        "client_id": client,
        "title": title,
        "brief_id": brief_id,
        "generated_on": today,
        "format": "markdown",
    }

    env = Environment(loader=BaseLoader())
    template = env.from_string(_REPORT_BODY_TEMPLATE)
    body = template.render(
        client_id=client,
        title=title,
        brief_id=brief_id,
        generated_on=today,
        executive_summary=executive_summary,
        research_context=research_context,
        hypotheses=data["hypotheses"],
        experiments=data["experiments"],
        all_results=data["all_results"],
        winners=data["winners"],
        recommendations=recommendations,
        next_experiments=next_experiments,
    )

    return frontmatter, body.strip()


# ---------------------------------------------------------------------------
# AI generation (optional — falls back gracefully when unavailable)
# ---------------------------------------------------------------------------

def _try_ai_generation(client: str, brief_id: str, title: str, data: dict) -> dict:
    """
    Attempt to generate summary, recommendations, and next experiments via
    the Anthropic API. Returns an empty dict on any failure so callers fall
    back to local logic.
    """
    try:
        return _generate_via_anthropic(client, brief_id, title, data)
    except Exception:
        return {}


def _generate_via_anthropic(client: str, brief_id: str, title: str, data: dict) -> dict:
    import json as _json
    import anthropic as _anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    n_hyp = len(data["hypotheses"])
    n_exp = len(data["experiments"])
    n_win = len(data["winners"])
    winner_titles = [w["title"] for w in data["winners"]]

    context = (
        f"Client: {client}\nBrief: {title}\n"
        f"Hypotheses tested: {n_hyp}\nExperiments run: {n_exp}\nWinners: {n_win}\n"
    )
    if winner_titles:
        context += "Winning results:\n" + "\n".join(f"- {t}" for t in winner_titles) + "\n"

    prompt = (
        "You are a research analyst. Based on this research summary, write three things.\n\n"
        f"{context}\n"
        "Return ONLY a JSON object with exactly three keys:\n"
        '  "summary": 2-3 sentence executive summary\n'
        '  "recommendations": array of 3-5 actionable strings\n'
        '  "next_experiments": array of 2-4 follow-up experiment strings\n'
        "No markdown fences, no explanation — raw JSON only."
    )

    ai = _anthropic.Anthropic(api_key=api_key)
    msg = ai.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) >= 2 else raw

    return _json.loads(raw)


# ---------------------------------------------------------------------------
# Fallback generators (always work offline)
# ---------------------------------------------------------------------------

def _build_research_context(brief_fm: dict, brief_body: str) -> str:
    title = brief_fm.get("title", "Research Brief")
    status = brief_fm.get("status", "")
    created = brief_fm.get("created", "")

    lines = [f"**Brief:** {title}"]
    if status:
        lines.append(f"**Status:** `{status}`")
    if created:
        lines.append(f"**Created:** {created}")

    first_para = next(
        (line.strip() for line in brief_body.splitlines()
         if line.strip() and not line.strip().startswith("#")),
        "",
    )
    if first_para:
        lines.append(f"\n{first_para}")

    return "\n".join(lines)


def _build_fallback_summary(data: dict, title: str) -> str:
    client = data["client"]
    n_hyp = len(data["hypotheses"])
    n_exp = len(data["experiments"])
    n_win = len(data["winners"])

    parts = [
        f"This report summarizes the research conducted for **{client}** "
        f"under the brief **{title}**.",
        "",
        f"A total of **{n_hyp}** hypothesis/hypotheses were tested across "
        f"**{n_exp}** experiment(s).",
    ]

    if n_win > 0:
        top = data["winners"][0]
        parts.append(
            f"**{n_win}** winning result(s) were identified. "
            f"The top performer was _{top['title']}_ "
            f"with {round(top['confidence'] * 100, 1)}% confidence."
        )
    else:
        parts.append(
            "No winners have been confirmed yet — experiments may still be in progress."
        )

    return "\n".join(parts)


def _build_fallback_recommendations(data: dict) -> list:
    recs = []

    for w in data["winners"]:
        recs.append(
            f"Promote the winning condition from _{w['title']}_ to production "
            f"(confidence: {round(w['confidence'] * 100, 1)}%)."
        )

    untested = [
        h for h in data["hypotheses"]
        if not h.get("experiments")
    ]
    for h in untested[:2]:
        recs.append(f"Design an experiment to test: _{h['title']}_.")

    if not recs:
        recs.append(
            "Review and finalize all pending experiments before planning next steps."
        )

    return recs


def _build_fallback_next_experiments(data: dict) -> list:
    suggestions = []

    exp_ids_with_results = {r["experiment_id"] for r in data["all_results"]}
    for exp in data["experiments"]:
        if exp["id"] not in exp_ids_with_results:
            suggestions.append(
                f"Log results for experiment: _{exp['id']} — {exp['title']}_."
            )

    hyp_ids_with_experiments = {e["hypothesis_id"] for e in data["experiments"]}
    for hyp in data["hypotheses"]:
        if hyp["id"] not in hyp_ids_with_experiments:
            suggestions.append(f"Create an experiment to test: _{hyp['title']}_.")

    for w in data["winners"]:
        suggestions.append(
            f"Design a follow-up experiment to extend: _{w['title']}_."
        )

    if not suggestions:
        suggestions.append(
            "All current hypotheses have been tested. Define new research questions for the next cycle."
        )

    return suggestions

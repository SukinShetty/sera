"""
cli/commands/ask.py — One command from question to evidenced answer.

Command:
    sera ask "QUESTION" [--client SLUG] [--max-hypotheses 3]
                        [--timeout 300] [--no-report]

Pipeline: question → brief → hypotheses → one generated + executed
experiment per hypothesis → ANSWER panel + per-hypothesis results table
→ compiled client report.
"""

import re
from datetime import date, datetime

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown

console = Console()


def _engine_available() -> bool:
    try:
        import engine  # noqa: F401
        return True
    except ImportError:
        return False


@click.command("ask")
@click.argument("question")
@click.option("--client", "client", default=None, help="Client slug (derived from the question if omitted).")
@click.option("--max-hypotheses", default=3, show_default=True, help="Maximum hypotheses to test.")
@click.option("--timeout", default=300, show_default=True, help="Max seconds per experiment script run.")
@click.option("--no-report", is_flag=True, help="Skip compiling the final client report.")
@click.option("--memory/--no-memory", "memory", default=True, show_default=True,
              help="Condition hypothesis generation on past outcomes from the ledger.")
def ask(question, client, max_hypotheses, timeout, no_report, memory):
    """Answer a research QUESTION with generated, executed experiments."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print(f"   Would research: [bold]{question}[/bold]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine import ledger
    from engine.hypothesis import generate as generate_hypotheses
    from engine.experiment import create as create_experiment
    from engine.scriptgen import generate_script

    client = client or _slug_from_question(question)
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    client_root = clients_root / client

    if client_root.exists():
        console.print(f"Reusing client vault: [bold]{client}[/bold]")
    else:
        for sub in ("briefs", "hypotheses", "experiments", "results"):
            ensure_dir(client_root / sub)
        console.print(f"Created client vault: [bold]{client}[/bold]")

    with console.status("Writing research brief..."):
        brief_id = _write_brief(client_root, client, question)
    console.print(f"[green]OK[/green] Brief written: {brief_id}")

    with console.status("Generating hypotheses..."):
        hyp_ids = generate_hypotheses(client, brief_id, memory=memory)[:max_hypotheses]
    console.print(f"[green]OK[/green] {len(hyp_ids)} hypotheses generated (memory {'on' if memory else 'off'})")

    rows = []
    for i, hyp_id in enumerate(hyp_ids, 1):
        hyp_fm, _ = read_markdown(client_root / "hypotheses" / f"{hyp_id}.md")
        title = hyp_fm.get("title", hyp_id)
        predicted = hyp_fm.get("predicted_winner", "")
        console.print(f"[{i}/{len(hyp_ids)}] Testing: [bold]{title}[/bold] (predicts: {predicted})")

        summary = None
        try:
            exp_id = create_experiment(client, hyp_id)
            with console.status(f"[{i}/{len(hyp_ids)}] Claude is writing and running the experiment..."):
                summary = generate_script(client, exp_id, timeout=timeout)
            rows.append({"title": title, "summary": summary, "status": "ok"})
            console.print(
                f"    [green]done[/green] winner={summary['winner']['winner_condition']} "
                f"({summary['metric']}={summary['winner']['winner_value']})"
            )
        except Exception as exc:  # noqa: BLE001 — one failure must not sink the ask
            rows.append({"title": title, "summary": None, "status": "FAILED"})
            console.print(f"    [red]FAILED[/red] {escape(str(exc))}")

        ledger.record(_ledger_entry(client, brief_id, question, hyp_id, title, predicted, summary))

    succeeded = [r for r in rows if r["status"] == "ok"]
    if not succeeded:
        raise click.ClickException(
            f"All {len(rows)} experiments failed after repairs. "
            f"See the scriptgen-*.log files in {PROJECT_ROOT / CONFIG['paths']['logs_root'] / client}"
        )

    _print_answer(question, rows, client_root, client)

    if not no_report:
        from reports.generator import generate as generate_report
        with console.status("Compiling client report..."):
            report_path = generate_report(client, brief_id)
        console.print(f"  Report: {report_path}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slug_from_question(question: str) -> str:
    """Derive a stable client slug from the question's key words."""
    stop = {
        "a", "an", "and", "are", "at", "do", "does", "for", "how", "in",
        "is", "it", "more", "most", "of", "on", "or", "the", "to", "what",
        "which", "with",
    }
    words = re.sub(r"[^a-z0-9\s]", "", question.lower()).split()
    core = [w for w in words if w not in stop][:4] or words[:4] or ["question"]
    return ("ask-" + "-".join(core))[:40].rstrip("-")


def _write_brief(client_root, client: str, question: str) -> str:
    """Write the question as the next brief-NNN in the client vault."""
    briefs_dir = client_root / "briefs"
    ensure_dir(briefs_dir)
    existing = sorted(briefs_dir.glob("brief-*.md"))
    brief_id = f"brief-{len(existing) + 1:03d}"

    title = question if len(question) <= 80 else question[:77] + "..."
    write_markdown(
        briefs_dir / f"{brief_id}.md",
        body=(
            f"# Research Brief: {title}\n\n"
            "## Objective\n\n"
            f"{question}\n\n"
            "## Research Questions\n\n"
            f"1. {question}\n"
        ),
        frontmatter={
            "title": title,
            "client_id": client,
            "status": "active",
            "created": date.today().isoformat(),
        },
    )
    return brief_id


def _ledger_entry(client, brief_id, question, hyp_id, title, predicted, summary):
    """Build one outcome-ledger entry for a completed or failed experiment."""
    from engine import ledger

    actual = summary["winner"]["winner_condition"] if summary else None
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "client": client,
        "brief_id": brief_id,
        "question": question,
        "hypothesis_id": hyp_id,
        "hypothesis_title": title,
        "predicted_winner": predicted,
        "actual_winner": actual,
        "verdict": ledger.compute_verdict(predicted, actual),
        "metric": summary["metric"] if summary else None,
        "winner_value": summary["winner"]["winner_value"] if summary else None,
        "conditions": summary["conditions"] if summary else None,
        "mode": summary["mode"] if summary else None,
        "attempts": summary["attempts"] if summary else None,
    }


def _condition_vote(rows):
    """
    Vote across succeeded rows: the answer is the condition that won the
    most experiments. Ties break by mean normalized margin — winner_value
    minus runner-up, scaled by each experiment's value range — then by
    label for determinism. Raw winner values are never compared across
    experiments (their metrics have incommensurable scales).

    Returns (display_label, wins, mean_margin).
    """
    votes = {}
    for row in rows:
        summary = row["summary"]
        label = summary["winner"]["winner_condition"]
        values = sorted((float(v) for v in summary["conditions"].values()), reverse=True)
        top, low = values[0], values[-1]
        runner_up = values[1] if len(values) > 1 else top
        margin = (top - runner_up) / (top - low) if top > low else 0.0
        votes.setdefault(label.strip().lower(), {"display": label, "margins": []})["margins"].append(margin)

    def rank(item):
        key, v = item
        return (len(v["margins"]), sum(v["margins"]) / len(v["margins"]), key)

    _, best = max(votes.items(), key=rank)
    mean_margin = sum(best["margins"]) / len(best["margins"])
    return best["display"], len(best["margins"]), round(mean_margin, 4)


def _guard_same_metric(label, succeeded):
    """
    Degenerate-winner guard. A condition may never be crowned while a
    condition sharing its metric scored strictly higher. For every
    experiment `label` won, compare its winning value against every
    same-metric peer value across all experiments; if any peer is strictly
    higher, prefer that peer instead. Same metric name = commensurable
    scale, so the comparison is valid.

    Returns the label to crown (possibly unchanged).
    """
    lab = label.strip().lower()
    chosen_label, chosen_val = label, None
    for row in succeeded:
        summary = row["summary"]
        if summary["winner"]["winner_condition"].strip().lower() != lab:
            continue
        metric = summary["metric"]
        own_value = float(summary["winner"]["winner_value"])
        for other in succeeded:
            other_summary = other["summary"]
            if other_summary["metric"] != metric:
                continue
            for peer_label, peer_value in other_summary["conditions"].items():
                if peer_label.strip().lower() == lab:
                    continue
                peer_value = float(peer_value)
                if peer_value > own_value and (chosen_val is None or peer_value > chosen_val):
                    chosen_label, chosen_val = peer_label, peer_value
    return chosen_label


def _synthesize_answer(succeeded):
    """
    Metric-aware winner synthesis across succeeded experiments.

    Experiments sharing a metric NAME are on a commensurable scale, so
    their values may be compared directly; values from DIFFERENT metric
    names must never be compared by raw value (that would reintroduce the
    inverse of the bug this fixes).

    - If one metric name dominates — the unique most-common metric, shared
      by at least 2 experiments — the answer is the condition with the
      highest actual value on that shared metric ("shared-metric" path).
      Each experiment's winner is that experiment's max on the metric, so
      the top winner value is the true maximum across all conditions.
    - Otherwise the metrics are incommensurable: fall back to counting
      experiment wins ("different-metric" path), guarded so a condition is
      never crowned while a same-metric peer scored strictly higher.

    Returns a dict:
        {condition, path, metric, value, shared_count, wins, total, mean_margin}
    where path is "shared-metric" or "different-metric" and the fields not
    relevant to that path are None.
    """
    total = len(succeeded)
    groups = {}
    for row in succeeded:
        groups.setdefault(row["summary"]["metric"], []).append(row)

    counts = {metric: len(group) for metric, group in groups.items()}
    max_count = max(counts.values())
    top_metrics = [metric for metric, count in counts.items() if count == max_count]

    if max_count >= 2 and len(top_metrics) == 1:
        metric = top_metrics[0]
        peers = groups[metric]
        best = max(peers, key=lambda r: float(r["summary"]["winner"]["winner_value"]))
        return {
            "condition": best["summary"]["winner"]["winner_condition"],
            "path": "shared-metric",
            "metric": metric,
            "value": best["summary"]["winner"]["winner_value"],
            "shared_count": len(peers),
            "wins": None,
            "total": total,
            "mean_margin": None,
        }

    voted_label, _, mean_margin = _condition_vote(succeeded)
    label = _guard_same_metric(voted_label, succeeded)
    wins = sum(1 for r in succeeded
               if r["summary"]["winner"]["winner_condition"].strip().lower() == label.strip().lower())
    return {
        "condition": label,
        "path": "different-metric",
        "metric": None,
        "value": None,
        "shared_count": None,
        "wins": wins,
        "total": total,
        "mean_margin": mean_margin,
    }


def _print_answer(question, rows, client_root, client):
    """Render the ANSWER panel, per-hypothesis table, and evidence paths."""
    succeeded = [r for r in rows if r["status"] == "ok"]
    answer = _synthesize_answer(succeeded)
    answer_label = answer["condition"]

    if answer["path"] == "shared-metric":
        headline = (
            f"[bold]{answer_label}[/bold] — best {answer['metric']} at "
            f"{answer['value']} (compared across {answer['shared_count']} "
            "experiments sharing this metric)"
        )
    else:
        headline = (
            "Experiments used different metrics; no single comparable winner. "
            f"By experiment wins: [bold]{answer_label}[/bold] won "
            f"{answer['wins']} of {answer['total']}."
        )

    console.print(Panel(
        f"{headline}\n\n[dim]Question: {escape(question)}[/dim]",
        title="ANSWER",
        border_style="green",
    ))

    table = Table(title=f"Evidence: {len(succeeded)}/{len(rows)} experiments succeeded")
    table.add_column("Hypothesis", style="cyan")
    table.add_column("Winner")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_column("Mode")
    table.add_column("Attempts", justify="right")
    table.add_column("Status", justify="center")

    for row in rows:
        if row["status"] == "ok":
            summary = row["summary"]
            is_answer = summary["winner"]["winner_condition"].strip().lower() == answer_label.strip().lower()
            style = "bold green" if is_answer else None
            table.add_row(
                row["title"],
                summary["winner"]["winner_condition"],
                summary["metric"],
                str(summary["winner"]["winner_value"]),
                summary["mode"],
                str(summary["attempts"]),
                "ok",
                style=style,
            )
        else:
            table.add_row(row["title"], "-", "-", "-", "-", "-", "[red]FAILED[/red]")

    console.print(table)

    console.print("Evidence:")
    console.print(f"  Vault:    {client_root}")
    console.print(f"  Run logs: {PROJECT_ROOT / CONFIG['paths']['logs_root'] / client}")

    if any(r["status"] == "ok" and r["summary"]["mode"] == "simulation" for r in rows):
        console.print(
            "[yellow]Note: results include simulated experiments -- "
            "they measure real algorithms on synthetic data.[/yellow]"
        )

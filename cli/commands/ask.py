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
from datetime import date

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
def ask(question, client, max_hypotheses, timeout, no_report):
    """Answer a research QUESTION with generated, executed experiments."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print(f"   Would research: [bold]{question}[/bold]")
        console.print("   Run Session 3 to enable this command.")
        return

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
        hyp_ids = generate_hypotheses(client, brief_id)[:max_hypotheses]
    console.print(f"[green]OK[/green] {len(hyp_ids)} hypotheses generated")

    rows = []
    for i, hyp_id in enumerate(hyp_ids, 1):
        hyp_fm, _ = read_markdown(client_root / "hypotheses" / f"{hyp_id}.md")
        title = hyp_fm.get("title", hyp_id)
        console.print(f"[{i}/{len(hyp_ids)}] Testing: [bold]{title}[/bold]")

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


def _print_answer(question, rows, client_root, client):
    """Render the ANSWER panel, per-hypothesis table, and evidence paths."""
    succeeded = [r for r in rows if r["status"] == "ok"]
    best = max(succeeded, key=lambda r: r["summary"]["winner"]["winner_value"])
    winner = best["summary"]["winner"]

    console.print(Panel(
        f"[bold]{winner['winner_condition']}[/bold] performed best: "
        f"{best['summary']['metric']} = {winner['winner_value']}\n\n"
        f"[dim]Question: {escape(question)}[/dim]",
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
            style = "bold green" if row is best else None
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

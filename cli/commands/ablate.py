"""
cli/commands/ablate.py — Ablate command.

Command:
    sera ablate [--briefs PATH] [--cycles 3] [--repeats 1] [--dry-run] [--yes]

Runs the memory ablation harness: the same brief set through the full ask
pipeline with memory on vs off, measuring Hypothesis Survival Rate per cycle.
"""

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _engine_available() -> bool:
    try:
        import engine  # noqa: F401
        return True
    except ImportError:
        return False


@click.command("ablate")
@click.option("--briefs", "briefs_path", default="experiments/ablation/briefs.jsonl",
              show_default=True, help="JSONL brief set: one {id, question} per line.")
@click.option("--cycles", default=3, show_default=True, help="Passes over the brief set per arm.")
@click.option("--repeats", default=1, show_default=True, help="Independent repeats per arm.")
@click.option("--dry-run", is_flag=True, help="Deterministic offline mock — no API calls, no cost.")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt for real (paid) runs.")
def ablate(briefs_path, cycles, repeats, dry_run, yes):
    """Run the memory-on vs memory-off ablation experiment."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine.ablation import _load_briefs, run_ablation

    briefs = _load_briefs(briefs_path)
    arms = 2
    total_asks = len(briefs) * cycles * arms * repeats
    total_hypotheses = total_asks * 3

    console.print(f"Plan: {len(briefs)} briefs x {cycles} cycles x {arms} arms x {repeats} repeats "
                  f"= [bold]{total_asks} asks[/bold] (~{total_hypotheses} generated experiments)")

    if dry_run:
        console.print("[yellow]Dry run:[/yellow] deterministic offline mock — no API calls, no cost.")
    else:
        console.print(f"Each ask makes ~4-8 Claude calls (hypotheses + scripts + repairs): "
                      f"expect roughly {total_asks * 6} API calls. This costs real money "
                      "and can take hours.")
        if not yes:
            click.confirm("Proceed with the real run?", abort=True)

    from engine.api import BillingError

    try:
        summary = run_ablation(
            briefs_path,
            cycles=cycles,
            repeats=repeats,
            dry_run=dry_run,
            progress=lambda message: console.print(f"[dim]{message}[/dim]"),
        )
    except BillingError as exc:
        console.print(
            "\n[bold red]ABORTED: Anthropic credit balance exhausted.[/bold red]\n"
            f"[red]{exc}[/red]\n"
            "The run halted immediately. Partial results.jsonl and per-arm "
            "ledgers on disk are valid (append-only). Top up credits and "
            "restart the run.")
        raise SystemExit(1)

    table = Table(title="Hypothesis Survival Rate (memory ablation)")
    table.add_column("Arm", style="cyan", no_wrap=True)
    table.add_column("Cycle", justify="right")
    table.add_column("HSR mean", justify="right")
    table.add_column("HSR std", justify="right")
    table.add_column("Survived", justify="right")
    table.add_column("Killed", justify="right")
    table.add_column("Failed", justify="right")

    for arm, arm_data in summary["arms"].items():
        for cycle_stat in arm_data["cycles"]:
            table.add_row(
                f"memory-{arm}",
                str(cycle_stat["cycle"]),
                f"{cycle_stat['hsr_mean']:.4f}",
                f"{cycle_stat['hsr_std']:.4f}",
                str(cycle_stat["survived"]),
                str(cycle_stat["killed"]),
                str(cycle_stat["failed"]),
            )

    console.print(table)
    for arm, arm_data in summary["arms"].items():
        console.print(f"  memory-{arm} overall HSR: [bold]{arm_data['overall_hsr']:.4f}[/bold]")
    console.print(f"  Curve:   {summary['paths']['png']}")
    console.print(f"  Data:    {summary['paths']['csv']}")
    console.print(f"  Summary: {summary['paths']['summary']}")

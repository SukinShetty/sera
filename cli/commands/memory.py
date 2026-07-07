"""
cli/commands/memory.py — Memory command group.

Commands:
    sera memory stats
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


@click.group()
def memory():
    """Inspect SERA's research outcome memory."""
    pass


@memory.command("stats")
def memory_stats():
    """Show outcome ledger statistics."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine.ledger import stats  # type: ignore[import]
    s = stats()

    if s["total"] == 0:
        console.print("[yellow]The outcome ledger is empty.[/yellow]")
        console.print("Run 'sera ask \"...\"' to start recording research outcomes.")
        return

    table = Table(title="SERA Outcome Memory")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right")

    table.add_row("Total outcomes", str(s["total"]))
    table.add_row("Survived", f"[green]{s['survived']}[/green]")
    table.add_row("Killed", f"[red]{s['killed']}[/red]")
    table.add_row("Failed", f"[yellow]{s['failed']}[/yellow]")
    table.add_row("Survival rate", f"{s['survival_rate'] * 100:.1f}%")

    console.print(table)

    clients = Table(title="Outcomes per Client")
    clients.add_column("Client", style="cyan", no_wrap=True)
    clients.add_column("Outcomes", justify="right")
    for client, count in sorted(s["by_client"].items()):
        clients.add_row(client, str(count))

    console.print(clients)

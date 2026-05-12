"""
cli/commands/hypothesis.py — Hypothesis command group.

Commands:
    sera hypothesis generate --client <name> --brief <brief_id>
    sera hypothesis list --client <name>
"""

import click
from rich.console import Console
from rich.table import Table
from shared.config import CONFIG, PROJECT_ROOT

console = Console()


def _engine_available() -> bool:
    try:
        import engine  # noqa: F401
        return True
    except ImportError:
        return False


@click.group()
def hypothesis():
    """Manage research hypotheses."""
    pass


@hypothesis.command("generate")
@click.option("--client", required=True, help="Client name.")
@click.option("--brief", required=True, help="Brief ID to generate hypotheses for.")
def hypothesis_generate(client, brief):
    """Generate hypotheses for a research brief."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print(f"   Would generate hypotheses for client=[bold]{client}[/bold], brief=[bold]{brief}[/bold]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine.hypothesis import generate  # type: ignore[import]
    generate(client=client, brief_id=brief)


@hypothesis.command("list")
@click.option("--client", required=True, help="Client name.")
def hypothesis_list(client):
    """List all hypotheses for a client."""
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    hyp_path = clients_root / client / "hypotheses"

    if not hyp_path.exists():
        console.print(f"[red]No hypothesis folder found for '{client}'.[/red]")
        console.print("Run 'sera vault init --client <name>' first.")
        return

    files = sorted(hyp_path.glob("*.md"))

    if not files:
        console.print(f"[yellow]No hypotheses found for '{client}'.[/yellow]")
        return

    table = Table(title=f"Hypotheses: {client}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("File")

    for i, f in enumerate(files, 1):
        table.add_row(str(i), f.name)

    console.print(table)

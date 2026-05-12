"""
cli/commands/experiment.py — Experiment command group.

Commands:
    sera experiment create --client <name> --hypothesis <hyp_id>
    sera experiment list --client <name>
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
def experiment():
    """Manage research experiments."""
    pass


@experiment.command("create")
@click.option("--client", required=True, help="Client name.")
@click.option("--hypothesis", "hyp_id", required=True, help="Hypothesis ID to run an experiment for.")
def experiment_create(client, hyp_id):
    """Create a new experiment for a hypothesis."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print(f"   Would create experiment for client=[bold]{client}[/bold], hypothesis=[bold]{hyp_id}[/bold]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine.experiment import create  # type: ignore[import]
    create(client=client, hypothesis_id=hyp_id)


@experiment.command("list")
@click.option("--client", required=True, help="Client name.")
def experiment_list(client):
    """List all experiments for a client."""
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    exp_path = clients_root / client / "experiments"

    if not exp_path.exists():
        console.print(f"[red]No experiment folder found for '{client}'.[/red]")
        console.print("Run 'sera vault init --client <name>' first.")
        return

    files = sorted(exp_path.glob("*.md"))

    if not files:
        console.print(f"[yellow]No experiments found for '{client}'.[/yellow]")
        return

    table = Table(title=f"Experiments: {client}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("File")

    for i, f in enumerate(files, 1):
        table.add_row(str(i), f.name)

    console.print(table)

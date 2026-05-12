"""
cli/commands/vault.py — Vault command group.

Commands:
    sera vault init --client <name>
    sera vault list
    sera vault status --client <name>
"""

import click
from rich.console import Console
from rich.table import Table
from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir

console = Console()


@click.group()
def vault():
    """Manage SERA client vaults."""
    pass


@vault.command("init")
@click.option("--client", required=True, help="Client name (used as the vault folder name).")
def vault_init(client):
    """Initialize a new client vault with folder structure."""
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    client_path = clients_root / client

    if client_path.exists():
        console.print(f"[yellow]Vault for '{client}' already exists:[/yellow] {client_path}")
        return

    for subdir in ["briefs", "hypotheses", "experiments", "reports"]:
        ensure_dir(client_path / subdir)

    console.print(f"[green]OK[/green] Created vault for client '[bold]{client}[/bold]'")
    console.print(f"  Location: {client_path}")
    console.print("  Folders:  briefs/  hypotheses/  experiments/  reports/")


@vault.command("list")
def vault_list():
    """List all client vaults."""
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]

    if not clients_root.exists() or not any(clients_root.iterdir()):
        console.print("[yellow]No clients found.[/yellow] Run 'sera vault init --client <name>' to create one.")
        return

    clients = sorted(p for p in clients_root.iterdir() if p.is_dir())

    table = Table(title="SERA Client Vaults")
    table.add_column("Client", style="cyan", no_wrap=True)
    table.add_column("Briefs", justify="right")
    table.add_column("Hypotheses", justify="right")
    table.add_column("Experiments", justify="right")
    table.add_column("Reports", justify="right")

    for client in clients:
        def count(sub):
            path = client / sub
            return str(len(list(path.iterdir()))) if path.exists() else "[red]-[/red]"

        table.add_row(
            client.name,
            count("briefs"),
            count("hypotheses"),
            count("experiments"),
            count("reports"),
        )

    console.print(table)


@vault.command("status")
@click.option("--client", required=True, help="Client name.")
def vault_status(client):
    """Show vault status for a client."""
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    client_path = clients_root / client

    if not client_path.exists():
        console.print(f"[red]No vault found for client '{client}'.[/red]")
        console.print("Run 'sera vault init --client <name>' to create one.")
        return

    table = Table(title=f"Vault Status: {client}")
    table.add_column("Section", style="cyan")
    table.add_column("Items", justify="right")
    table.add_column("Path", style="dim")

    for subdir in ["briefs", "hypotheses", "experiments", "reports"]:
        subpath = client_path / subdir
        if subpath.exists():
            items = len(list(subpath.iterdir()))
            table.add_row(subdir, str(items), str(subpath))
        else:
            table.add_row(subdir, "[red]missing[/red]", str(subpath))

    console.print(table)

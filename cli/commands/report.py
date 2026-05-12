"""
cli/commands/report.py — Report command group.

Commands:
    sera report generate --client <name> --brief <brief_id>
    sera report list --client <name>
"""

import click
from rich.console import Console
from rich.table import Table
from shared.config import CONFIG, PROJECT_ROOT

console = Console()


def _reports_available() -> bool:
    try:
        import reports  # noqa: F401
        return True
    except ImportError:
        return False


@click.group()
def report():
    """Manage research reports."""
    pass


@report.command("generate")
@click.option("--client", required=True, help="Client name.")
@click.option("--brief", required=True, help="Brief ID to generate a report for.")
def report_generate(client, brief):
    """Generate a research report for a brief."""
    if not _reports_available():
        console.print("[yellow]WARNING: Reports module not yet available (built in Session 4).[/yellow]")
        console.print(f"   Would generate report for client=[bold]{client}[/bold], brief=[bold]{brief}[/bold]")
        console.print("   Run Session 4 to enable this command.")
        return

    from reports.generator import generate  # type: ignore[import]
    generate(client=client, brief_id=brief)


@report.command("list")
@click.option("--client", required=True, help="Client name.")
def report_list(client):
    """List all reports for a client."""
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    vault_reports = clients_root / client / "reports"

    reports_root = PROJECT_ROOT / CONFIG["paths"]["reports_root"]
    output_reports = reports_root / client

    files = []
    for path in [vault_reports, output_reports]:
        if path.exists():
            files.extend(path.glob("*.md"))

    if not files:
        console.print(f"[yellow]No reports found for '{client}'.[/yellow]")
        return

    table = Table(title=f"Reports: {client}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("File")

    for i, f in enumerate(sorted(files), 1):
        table.add_row(str(i), f.name)

    console.print(table)

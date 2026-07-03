"""
cli/commands/experiment.py — Experiment command group.

Commands:
    sera experiment create --client <name> --hypothesis <hyp_id>
    sera experiment list --client <name>
    sera experiment attach CLIENT EXP_ID SCRIPT_PATH
    sera experiment run CLIENT EXP_ID [--timeout 300]
    sera experiment generate CLIENT EXP_ID [--and-run/--no-run]
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


@experiment.command("attach")
@click.argument("client")
@click.argument("exp_id")
@click.argument("script_path", type=click.Path())
def experiment_attach(client, exp_id, script_path):
    """Attach an executable Python script to an experiment."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print(f"   Would attach script=[bold]{script_path}[/bold] to experiment=[bold]{exp_id}[/bold]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine.runner import attach_script  # type: ignore[import]
    dest = attach_script(client=client, experiment_id=exp_id, script_path=script_path)
    console.print(f"[green]OK[/green] Attached script to experiment '[bold]{exp_id}[/bold]' for client '[bold]{client}[/bold]'")
    console.print(f"  Script: {dest}")
    console.print(f"  Run it with: sera experiment run {client} {exp_id}")


@experiment.command("run")
@click.argument("client")
@click.argument("exp_id")
@click.option("--timeout", default=300, show_default=True, help="Max seconds to allow the script to run.")
def experiment_run(client, exp_id, timeout):
    """Execute an experiment's attached script and record results."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print(f"   Would run experiment=[bold]{exp_id}[/bold] for client=[bold]{client}[/bold]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine.runner import run  # type: ignore[import]
    summary = run(client=client, experiment_id=exp_id, timeout=timeout)
    _print_run_summary(client, exp_id, summary)


@experiment.command("generate")
@click.argument("client")
@click.argument("exp_id")
@click.option("--and-run/--no-run", "and_run", default=True, show_default=True,
              help="Execute the generated script after validation, or stop after attaching it.")
def experiment_generate(client, exp_id, and_run):
    """Generate an experiment script with Claude, validate it, and run it."""
    if not _engine_available():
        console.print("[yellow]WARNING: Engine module not yet available (built in Session 3).[/yellow]")
        console.print(f"   Would generate a script for experiment=[bold]{exp_id}[/bold], client=[bold]{client}[/bold]")
        console.print("   Run Session 3 to enable this command.")
        return

    from engine.scriptgen import generate_script  # type: ignore[import]
    summary = generate_script(client=client, experiment_id=exp_id, and_run=and_run)

    if and_run:
        _print_run_summary(client, exp_id, summary)
    else:
        console.print(f"[green]OK[/green] Generated and attached script for '[bold]{exp_id}[/bold]' (not run)")
        console.print(f"  Script: {summary['script_path']}")
        console.print(f"  Run it with: sera experiment run {client} {exp_id}")

    console.print(f"  Claude attempts: {summary['attempts']}")
    mode_style = "yellow" if summary["mode"] == "simulation" else "green"
    console.print(f"  Mode: [{mode_style}]{summary['mode']}[/{mode_style}]")


def _print_run_summary(client, exp_id, summary):
    """Render the per-condition results table for a completed run."""
    winner_condition = summary["winner"]["winner_condition"]

    table = Table(title=f"Experiment Run: {exp_id} ({client})")
    table.add_column("Condition", style="cyan", no_wrap=True)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_column("Winner", justify="center")

    for condition, value in summary["conditions"].items():
        is_winner = condition == winner_condition
        style = "bold green" if is_winner else None
        table.add_row(
            condition,
            summary["metric"],
            str(value),
            "YES" if is_winner else "",
            style=style,
        )

    console.print(table)
    console.print(f"[green]OK[/green] Experiment '[bold]{exp_id}[/bold]' complete -- winner: [bold green]{winner_condition}[/bold green]")
    console.print(f"  Run log: {summary['log_path']}")

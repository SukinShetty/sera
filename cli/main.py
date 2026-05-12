"""
cli/main.py — Entry point for the `sera` CLI.

Run with:
    python -m cli.main [COMMAND] [OPTIONS]
    sera [COMMAND] [OPTIONS]  (after pip install -e .)
"""

import click
from cli.commands.vault import vault
from cli.commands.hypothesis import hypothesis
from cli.commands.experiment import experiment
from cli.commands.report import report


@click.group()
@click.version_option(version="0.1.0", prog_name="sera")
def sera():
    """SERA Vault OS: Self-Evolving Research Architecture.

    A local-first Research-as-a-Service OS integrated with Obsidian.
    """
    pass


sera.add_command(vault)
sera.add_command(hypothesis)
sera.add_command(experiment)
sera.add_command(report)


if __name__ == "__main__":
    sera()

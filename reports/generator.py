"""
reports/generator.py — Orchestrate the full report generation pipeline.

Public API:
    generate(client, brief_id) -> Path
        Compile vault data, format into a Markdown report, and write to disk.
        Returns the path to the written report file.
"""

from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir

from reports.compiler import compile_report_data
from reports.formatter import render_report
from reports.exporter import export


def generate(client: str, brief_id: str) -> Path:
    """
    Generate a complete research report for a client brief.

    Reads the brief, all linked hypotheses, experiments, and results from
    the vault. Formats them into a structured Markdown report using a Jinja2
    template, with AI-assisted summaries when ANTHROPIC_API_KEY is available.

    Args:
        client:   Client slug (e.g. "acme-corp").
        brief_id: Brief file ID (e.g. "brief-001"), without .md extension.

    Returns:
        Path to the written report file.

    Raises:
        FileNotFoundError: If the brief does not exist in the client vault.
    """
    data = compile_report_data(client, brief_id)
    frontmatter, body = render_report(data)
    report_id = _build_report_id(client, brief_id)
    return export(client, report_id, frontmatter, body)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_report_id(client: str, brief_id: str) -> str:
    """
    Generate a unique report ID, incrementing a sequence suffix if needed.

    Format: report-{brief_id}-{NNN}
    """
    reports_root = PROJECT_ROOT / CONFIG["paths"]["reports_root"]
    output_dir = reports_root / client
    ensure_dir(output_dir)

    base = f"report-{brief_id}"
    n = 1
    while (output_dir / f"{base}-{n:03d}.md").exists():
        n += 1
    return f"{base}-{n:03d}"

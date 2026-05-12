"""
reports/exporter.py — Write a rendered report to disk.

Public API:
    export(client, report_id, frontmatter, body) -> Path
        Writes the report to reports/output/{client}/{report_id}.md.
        Returns the path of the written file.
"""

from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, write_markdown


def export(client: str, report_id: str, frontmatter: dict, body: str) -> Path:
    """
    Write a rendered report to the reports output directory.

    Args:
        client:      Client slug (e.g. "acme-corp").
        report_id:   Unique report identifier (e.g. "report-brief-001-001").
        frontmatter: Dict of metadata fields for the report file header.
        body:        Rendered Markdown body string.

    Returns:
        Path to the written report file.
    """
    reports_root = PROJECT_ROOT / CONFIG["paths"]["reports_root"]
    output_dir = reports_root / client
    ensure_dir(output_dir)

    report_path = output_dir / f"{report_id}.md"
    write_markdown(report_path, body, frontmatter)
    return report_path

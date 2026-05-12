"""
reports/ — SERA Report Generator (Session 4)

Public API:
    from reports.generator import generate
    generate(client, brief_id) -> Path
        Compile, format, and write a research report for the given brief.
"""

from reports.generator import generate

__all__ = ["generate"]

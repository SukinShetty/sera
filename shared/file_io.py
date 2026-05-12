"""
shared/file_io.py — File reading and writing utilities for SERA.

This module handles all the file operations SERA needs:
  - Creating folders safely (ensure_dir)
  - Reading Obsidian-style Markdown notes with metadata (read_markdown)
  - Writing Markdown notes with metadata headers (write_markdown)

The "frontmatter" mentioned throughout is the metadata block at the top of
Obsidian notes — the section between the two --- lines. For example:

    ---
    title: Market Research Q1
    client: Acme Corp
    status: draft
    ---

    # Research Content Starts Here

Usage:
    from shared.file_io import ensure_dir, read_markdown, write_markdown
"""

from pathlib import Path
from typing import Optional, Tuple


def ensure_dir(path) -> Path:
    """
    Create a folder (and any missing parent folders) if it doesn't exist yet.

    Safe to call multiple times — it will not fail or overwrite if the folder
    already exists.

    Example:
        ensure_dir("vault/clients/acme/experiments")
        → creates vault/, clients/, acme/, and experiments/ if any are missing.

    Returns the Path object for the created (or existing) directory.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_markdown(file_path) -> Tuple[dict, str]:
    """
    Read a Markdown (.md) file and return its frontmatter and body separately.

    Obsidian notes store metadata at the top of the file between --- lines.
    This function splits that metadata out so you can work with it as a
    Python dictionary.

    Returns:
        (frontmatter_dict, body_text)
        - frontmatter_dict: dict of key-value pairs from the --- block
        - body_text: the rest of the note content as a plain string

    If the file has no frontmatter, frontmatter_dict will be empty ({}).

    Raises:
        FileNotFoundError — if the file does not exist.

    Example:
        fm, body = read_markdown("vault/clients/acme/hypothesis.md")
        print(fm["status"])   # → "draft"
        print(body[:100])     # → "# Hypothesis 1 ..."
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"\n[SERA File Error] Markdown file not found:\n  {file_path}\n"
            "Please check the path and try again."
        )

    content = file_path.read_text(encoding="utf-8")

    # Try to parse frontmatter: it must start with --- and have a closing ---
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_text = parts[1].strip()
            body = parts[2].strip()
            frontmatter = _parse_frontmatter(frontmatter_text)
            return frontmatter, body

    # No frontmatter found — return the full content as body
    return {}, content.strip()


def write_markdown(file_path, body: str, frontmatter: Optional[dict] = None) -> Path:
    """
    Write a Markdown file with an optional frontmatter metadata header.

    Automatically creates any missing parent folders. Overwrites the file if
    it already exists.

    Args:
        file_path: Where to save the file (e.g., "vault/clients/acme/note.md")
        body:      The main Markdown content of the note
        frontmatter: Optional dict of metadata to write at the top of the file

    Returns:
        The Path to the written file.

    Example:
        write_markdown(
            "vault/clients/acme/hypothesis.md",
            body="# Hypothesis\\n\\nUsers prefer shorter onboarding flows.",
            frontmatter={"title": "Onboarding Hypothesis", "status": "draft", "client": "Acme Corp"}
        )
    """
    file_path = Path(file_path)
    ensure_dir(file_path.parent)

    sections = []

    if frontmatter:
        sections.append("---")
        for key, value in frontmatter.items():
            # Wrap values in quotes if they contain special characters
            formatted_value = _format_frontmatter_value(value)
            sections.append(f"{key}: {formatted_value}")
        sections.append("---")
        sections.append("")  # blank line between frontmatter and body

    sections.append(body)

    file_path.write_text("\n".join(sections), encoding="utf-8")
    return file_path


def _parse_frontmatter(text: str) -> dict:
    """
    Parse a frontmatter block (the text between the --- delimiters) into a dict.

    Handles simple key: value pairs. Multi-line or nested YAML is not supported
    in this lightweight parser — use python-frontmatter package for advanced needs.
    """
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            # Strip surrounding quotes if present
            value = value.strip().strip('"').strip("'")
            result[key.strip()] = value
    return result


def _format_frontmatter_value(value) -> str:
    """
    Format a Python value for writing into a frontmatter block.
    Wraps strings containing special characters in quotes.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    value = str(value)
    # Wrap in quotes if the value contains : or starts with special chars
    if ":" in value or value.startswith(("-", "?", "{", "[")):
        return f'"{value}"'
    return value

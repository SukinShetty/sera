"""
vault/scaffold.py — Client vault creation and discovery for SERA.

Each client gets an isolated folder tree under vault/clients/{client_id}/ that
mirrors the research workflow: briefs → hypotheses → experiments → results.
A _meta.md file at the root of each client folder serves as the Obsidian entry
point for that client's work.
"""

from pathlib import Path
from datetime import date

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, write_markdown


# Sub-folders created inside every new client vault.
_CLIENT_SUBDIRS = ["briefs", "hypotheses", "experiments", "results"]


def create_client_vault(client_id: str) -> Path:
    """
    Create the standard folder tree for a new client inside vault/clients/.

    Directory layout created:
        vault/clients/{client_id}/
            _meta.md
            briefs/
            hypotheses/
            experiments/
            results/

    If the vault already exists this function is safe to call again — existing
    files are not overwritten, only missing directories are created.

    Args:
        client_id: Slug-style identifier for the client (e.g. "acme-corp").
                   Must be non-empty.

    Returns:
        The absolute Path to the client vault root directory.

    Raises:
        ValueError: If client_id is empty or contains path-separator characters.
    """
    client_id = client_id.strip()
    if not client_id:
        raise ValueError("[SERA Vault] client_id must not be empty.")
    if "/" in client_id or "\\" in client_id:
        raise ValueError(
            f"[SERA Vault] client_id must not contain path separators: {client_id!r}"
        )

    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    client_root = clients_root / client_id

    ensure_dir(client_root)
    for sub in _CLIENT_SUBDIRS:
        ensure_dir(client_root / sub)

    meta_path = client_root / "_meta.md"
    if not meta_path.exists():
        write_markdown(
            meta_path,
            body=_meta_body(client_id),
            frontmatter={
                "client_id": client_id,
                "created": date.today().isoformat(),
                "status": "active",
            },
        )

    return client_root


def list_vaults() -> list[str]:
    """
    Return the client IDs of all existing client vaults.

    Scans vault/clients/ and returns the name of every immediate sub-directory,
    sorted alphabetically. Returns an empty list if no vaults exist yet.

    Returns:
        Sorted list of client_id strings (e.g. ["acme-corp", "globex", "initech"]).
    """
    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]

    if not clients_root.exists():
        return []

    return sorted(
        entry.name
        for entry in clients_root.iterdir()
        if entry.is_dir()
    )


def _meta_body(client_id: str) -> str:
    return (
        f"# Client Vault: {client_id}\n\n"
        "## Overview\n\n"
        "_Add client background and engagement summary here._\n\n"
        "## Links\n\n"
        f"- [[briefs/]] — Research briefs\n"
        f"- [[hypotheses/]] — Generated hypotheses\n"
        f"- [[experiments/]] — Experiment records\n"
        f"- [[results/]] — Logged results\n"
    )

"""
vault/ — Obsidian vault scaffolding and template module for SERA.

Exposes:
    create_client_vault(client_id) — build a new client vault folder tree
    list_vaults()                  — return all known client IDs
"""

from vault.scaffold import create_client_vault, list_vaults

__all__ = ["create_client_vault", "list_vaults"]

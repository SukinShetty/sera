"""
tests/test_frontend_smoke.py — v0.2 frontend smoke tests.

Verifies that all SERA modules the frontend depends on are importable and
functional, and that the CLI entry point is unchanged.

Run with: python -m pytest tests/test_frontend_smoke.py -v

NOTE: This file intentionally does NOT import reports.compiler or
reports.generator at module level. test_smoke_reports.py monkeypatches
shared.config.PROJECT_ROOT before those modules are imported; importing them
here first would break that test isolation.
"""

import importlib
import importlib.util
import sys
import tempfile
from pathlib import Path
from datetime import date

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── 1. Core SERA imports still work ──────────────────────────────────────────

def test_vault_imports():
    from vault import create_client_vault, list_vaults
    assert callable(create_client_vault)
    assert callable(list_vaults)


def test_engine_imports():
    from engine.hypothesis import generate as gen_hyp
    from engine.experiment import create as create_exp
    from engine.results import log_result, list_results
    from engine.winner import select_winner
    assert callable(gen_hyp)
    assert callable(create_exp)
    assert callable(log_result)
    assert callable(list_results)
    assert callable(select_winner)


def test_reports_module_exists():
    # Use filesystem check to avoid importing reports.compiler, which would break
    # the monkeypatch in test_smoke_reports.py (reports/__init__.py triggers that import).
    reports_gen = Path(__file__).parent.parent / "reports" / "generator.py"
    assert reports_gen.exists(), f"reports/generator.py not found at {reports_gen}"


def test_shared_imports():
    from shared.config import PROJECT_ROOT, CONFIG
    from shared.file_io import read_markdown, write_markdown, ensure_dir
    assert PROJECT_ROOT.exists()
    assert isinstance(CONFIG, dict)
    assert callable(read_markdown)
    assert callable(write_markdown)
    assert callable(ensure_dir)


# ── 2. Frontend helper functions work end-to-end ─────────────────────────────

def test_frontend_helper_functions():
    """Verify the brief creation logic (as used by the frontend) works correctly."""
    from shared.file_io import write_markdown, ensure_dir, read_markdown

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        briefs_dir = tmp_path / "briefs"
        ensure_dir(briefs_dir)

        brief_path = briefs_dir / "brief-001.md"
        body = "# Research Brief: Test\n\n## Objective\n\nTest objective.\n"
        write_markdown(brief_path, body, {
            "title": "Test Brief",
            "client_id": "test-client",
            "status": "active",
            "created": date.today().isoformat(),
        })

        assert brief_path.exists()
        fm, read_body = read_markdown(brief_path)
        assert fm["title"] == "Test Brief"
        assert "Objective" in read_body


# ── 3. streamlit is installed ─────────────────────────────────────────────────

def test_streamlit_installed():
    spec = importlib.util.find_spec("streamlit")
    assert spec is not None, "streamlit is not installed — run: pip install streamlit"


# ── 4. CLI entry point unchanged ─────────────────────────────────────────────

def test_cli_entry_point_unchanged():
    """Verify the CLI main group ('sera') is still importable and intact."""
    cli_mod = importlib.import_module("cli.main")
    assert hasattr(cli_mod, "sera"), (
        "cli.main no longer exports 'sera' — CLI entry point may be broken"
    )

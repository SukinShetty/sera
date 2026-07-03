"""
tests/test_scriptgen.py — Tests for Claude-generated experiment scripts.

NO real API calls: the Anthropic client is mocked by installing a fake
`anthropic` module in sys.modules with canned responses.

Covers:
    - validate_script static checks (imports, calls, contract, syntax).
    - The repair loop: broken script then valid script → attempts == 2.
    - End-to-end with a canned valid script: results, winner, status.
    - Missing API key raises a helpful RuntimeError.

Run with:
    python -m pytest tests/test_scriptgen.py -v
"""

import shutil
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.file_io import ensure_dir, write_markdown, read_markdown


# ---------------------------------------------------------------------------
# Shared test configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent

_TEST_CONFIG = {
    "project": {"name": "SERA Vault OS"},
    "paths": {
        "clients_root": "vault/clients/",
        "templates_root": "vault/templates/",
        "experiments_root": "engine/experiments/",
        "logs_root": "engine/logs/",
        "reports_root": "reports/output/",
    },
    "llm": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "research": {
        "hypotheses_per_experiment": 3,
        "winning_threshold": 0.7,
        "report_format": "markdown",
    },
}

CLIENT = "test-scriptgen"
BRIEF_ID = "brief-001"

VALID_SCRIPT = '''\
import json
import random

random.seed(42)

print("MODE: simulation")
conditions = {}
for name, quality in (("baseline", 0.4), ("treatment", 0.7)):
    hits = sum(1 for _ in range(1000) if random.random() < quality)
    conditions[name] = round(hits / 1000, 4)
    print(f"condition={name} accuracy={conditions[name]}")

print("SERA_METRICS " + json.dumps({"metric": "accuracy", "conditions": conditions}))
'''

BROKEN_SCRIPT = '''\
import json
import socket

print("SERA_METRICS " + json.dumps({"metric": "x", "conditions": {"a": 1}}))
'''


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_test_clients():
    """Remove any vault/clients/test-* artifacts left in the real vault."""
    yield
    real_clients = PROJECT_ROOT / "vault" / "clients"
    if real_clients.exists():
        for leftover in real_clients.glob("test-*"):
            shutil.rmtree(leftover, ignore_errors=True)


@pytest.fixture
def scriptgen_env(tmp_path, monkeypatch):
    """
    Isolated scriptgen environment: patches PROJECT_ROOT + CONFIG in all
    engine modules, scaffolds a client vault with a brief, and sets a fake
    API key (the Anthropic client itself is mocked per-test).
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    import shared.config
    import engine.hypothesis
    import engine.experiment
    import engine.results
    import engine.winner
    import engine.runner
    import engine.scriptgen

    for mod in (
        shared.config,
        engine.hypothesis,
        engine.experiment,
        engine.results,
        engine.winner,
        engine.runner,
        engine.scriptgen,
    ):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONFIG", _TEST_CONFIG)

    client_root = tmp_path / "vault" / "clients" / CLIENT
    for sub in ("briefs", "hypotheses", "experiments", "results"):
        ensure_dir(client_root / sub)

    write_markdown(
        client_root / "briefs" / f"{BRIEF_ID}.md",
        body=(
            "# Research Brief: Duplicate Detection\n\n"
            "## Objective\n\nFind the most accurate near-duplicate detection strategy.\n"
        ),
        frontmatter={
            "title": "Duplicate Detection",
            "client_id": CLIENT,
            "status": "active",
            "created": "2026-07-03",
        },
    )
    return tmp_path


@pytest.fixture
def experiment_id(scriptgen_env, monkeypatch):
    """A freshly created experiment (brief → hypotheses → experiment)."""
    # hypothesis.generate must not hit the API either — clear the key just
    # for generation so its offline fallback runs, then restore it.
    import os
    key = os.environ.pop("ANTHROPIC_API_KEY")
    try:
        from engine.hypothesis import generate
        from engine.experiment import create
        hyp_ids = generate(CLIENT, BRIEF_ID)
        return create(CLIENT, hyp_ids[0])
    finally:
        os.environ["ANTHROPIC_API_KEY"] = key


def install_fake_anthropic(monkeypatch, responses):
    """
    Install a fake `anthropic` module in sys.modules whose client returns the
    canned responses in order (repeating the last one if exhausted).
    Returns the shared call-count state dict.
    """
    state = {"calls": 0}

    def _create(**kwargs):
        i = min(state["calls"], len(responses) - 1)
        state["calls"] += 1
        return SimpleNamespace(content=[SimpleNamespace(text=responses[i])])

    class Anthropic:
        def __init__(self, api_key=None):
            self.messages = SimpleNamespace(create=_create)

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return state


# ---------------------------------------------------------------------------
# TEST 1 — validate_script
# ---------------------------------------------------------------------------

class TestValidateScript:

    def test_accepts_known_good_script(self):
        from engine.scriptgen import validate_script
        assert validate_script(VALID_SCRIPT) == []

    def test_rejects_forbidden_import(self):
        from engine.scriptgen import validate_script
        violations = validate_script(BROKEN_SCRIPT)
        assert any("socket" in v for v in violations)

    def test_rejects_open_call(self):
        from engine.scriptgen import validate_script
        code = 'print("SERA_METRICS {}")\nopen("data.txt")\n'
        violations = validate_script(code)
        assert any("open" in v for v in violations)

    def test_rejects_missing_sera_metrics(self):
        from engine.scriptgen import validate_script
        violations = validate_script('print("results: 42")\n')
        assert any("SERA_METRICS" in v for v in violations)

    def test_rejects_syntax_error(self):
        from engine.scriptgen import validate_script
        violations = validate_script("def broken(:\n    pass\n")
        assert any("syntax error" in v for v in violations)


# ---------------------------------------------------------------------------
# TEST 2 — Repair loop
# ---------------------------------------------------------------------------

class TestRepairLoop:

    def test_broken_then_valid_script_takes_two_attempts(
        self, scriptgen_env, experiment_id, monkeypatch
    ):
        """A rejected first script must be repaired on the second attempt."""
        from engine.scriptgen import generate_script

        state = install_fake_anthropic(monkeypatch, [BROKEN_SCRIPT, VALID_SCRIPT])
        summary = generate_script(CLIENT, experiment_id)

        assert summary["attempts"] == 2
        assert state["calls"] == 2
        assert summary["winner"]["winner_condition"] == "treatment"

    def test_exhausted_repairs_raise_with_log_path(
        self, scriptgen_env, experiment_id, monkeypatch
    ):
        """Persistent failures must raise RuntimeError naming the attempt log."""
        from engine.scriptgen import generate_script

        install_fake_anthropic(monkeypatch, [BROKEN_SCRIPT])
        with pytest.raises(RuntimeError, match="attempt log"):
            generate_script(CLIENT, experiment_id, max_repair_attempts=1)


# ---------------------------------------------------------------------------
# TEST 3 — End-to-end with canned valid script
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_generate_script_end_to_end(self, scriptgen_env, experiment_id, monkeypatch):
        """Canned valid script: results logged, winner selected, status complete."""
        from engine.scriptgen import generate_script

        install_fake_anthropic(monkeypatch, [VALID_SCRIPT])
        summary = generate_script(CLIENT, experiment_id)

        assert summary["attempts"] == 1
        assert summary["mode"] == "simulation"

        results_dir = scriptgen_env / "vault" / "clients" / CLIENT / "results"
        result_files = [
            p for p in sorted(results_dir.glob("*.md"))
            if read_markdown(p)[0].get("experiment_id") == experiment_id
        ]
        assert len(result_files) == 2
        winner_flags = [read_markdown(p)[0]["winner"] for p in result_files]
        assert winner_flags.count("true") == 1

        exp_path = scriptgen_env / "vault" / "clients" / CLIENT / "experiments" / f"{experiment_id}.md"
        fm, _ = read_markdown(exp_path)
        assert fm["status"] == "complete"

        assert summary["log_path"].exists()


# ---------------------------------------------------------------------------
# TEST 4 — Missing API key
# ---------------------------------------------------------------------------

class TestNoApiKey:

    def test_missing_key_raises_helpful_error(self, scriptgen_env, experiment_id, monkeypatch):
        """Without ANTHROPIC_API_KEY, generation must fail loudly — no fallback."""
        from engine.scriptgen import generate_script

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            generate_script(CLIENT, experiment_id)

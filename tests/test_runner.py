"""
tests/test_runner.py — Tests for the SERA experiment execution engine.

Covers:
    - The reference experiment's SERA_METRICS output contract (subprocess).
    - The full runner pipeline end-to-end: brief → hypotheses → experiment →
      attach_script → run → results, winner, status, run log.
    - Runner error handling (no script attached, missing script path).

All engine tests run in an isolated temp directory (never touch the real
vault). The Anthropic API key is cleared so only the fallback generator runs.

Run with:
    python -m pytest tests/test_runner.py -v
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.file_io import ensure_dir, write_markdown, read_markdown


# ---------------------------------------------------------------------------
# Shared test configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
REF_SCRIPT = PROJECT_ROOT / "engine" / "experiments" / "ref_chunking_retrieval.py"

_TEST_CONFIG = {
    "project": {"name": "SERA Vault OS"},
    "paths": {
        "clients_root": "vault/clients/",
        "templates_root": "vault/templates/",
        "experiments_root": "engine/experiments/",
        "logs_root": "engine/logs/",
        "reports_root": "reports/output/",
    },
    "research": {
        "hypotheses_per_experiment": 3,
        "winning_threshold": 0.7,
        "report_format": "markdown",
    },
}

CLIENT = "test-runner-e2e"
BRIEF_ID = "brief-001"


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
def runner_env(tmp_path, monkeypatch):
    """
    Isolated runner environment: patches PROJECT_ROOT + CONFIG in all engine
    modules (including engine.runner) to point at tmp_path. Creates a minimal
    client vault with one brief. No ANTHROPIC_API_KEY so the fallback
    generator is used.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import shared.config
    import engine.hypothesis
    import engine.experiment
    import engine.results
    import engine.winner
    import engine.runner

    for mod in (
        shared.config,
        engine.hypothesis,
        engine.experiment,
        engine.results,
        engine.winner,
        engine.runner,
    ):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONFIG", _TEST_CONFIG)

    # Scaffold a minimal client vault
    client_root = tmp_path / "vault" / "clients" / CLIENT
    for sub in ("briefs", "hypotheses", "experiments", "results"):
        ensure_dir(client_root / sub)

    # Write a minimal brief
    brief_path = client_root / "briefs" / f"{BRIEF_ID}.md"
    write_markdown(
        brief_path,
        body=(
            "# Research Brief: RAG Chunking Strategy\n\n"
            "## Objective\n\nFind the chunking strategy with the best retrieval quality.\n\n"
            "## Research Questions\n\n"
            "1. Do fixed-size or paragraph chunks retrieve more accurately?\n"
            "2. How does chunk size affect ranking quality?\n"
        ),
        frontmatter={
            "title": "RAG Chunking Strategy",
            "client_id": CLIENT,
            "status": "active",
            "created": "2026-07-03",
        },
    )

    return tmp_path


@pytest.fixture
def experiment_id(runner_env):
    """A freshly created experiment (brief → hypotheses → experiment)."""
    from engine.hypothesis import generate
    from engine.experiment import create

    hyp_ids = generate(CLIENT, BRIEF_ID)
    return create(CLIENT, hyp_ids[0])


# ---------------------------------------------------------------------------
# TEST 1 — Reference experiment output contract
# ---------------------------------------------------------------------------

class TestReferenceExperimentContract:

    def test_reference_experiment_emits_contract(self):
        """The reference script must exit 0 and end with a valid SERA_METRICS line."""
        proc = subprocess.run(
            [sys.executable, str(REF_SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        assert proc.returncode == 0, f"Script failed:\n{proc.stderr}"

        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        assert lines, "Script produced no stdout"
        final = lines[-1]
        assert final.startswith("SERA_METRICS"), f"Final line is not SERA_METRICS: {final!r}"

        payload = json.loads(final[len("SERA_METRICS"):].strip())
        assert "metric" in payload, f"Missing 'metric' key: {payload}"
        assert "conditions" in payload, f"Missing 'conditions' key: {payload}"
        assert len(payload["conditions"]) == 3, f"Expected 3 conditions: {payload['conditions']}"
        for condition, value in payload["conditions"].items():
            assert isinstance(value, (int, float)), f"{condition} value is not numeric: {value!r}"


# ---------------------------------------------------------------------------
# TEST 2 — Runner end-to-end
# ---------------------------------------------------------------------------

class TestRunnerEndToEnd:

    def test_runner_end_to_end(self, runner_env, experiment_id):
        """Full pipeline: attach the reference script, run it, verify artifacts."""
        from engine.runner import attach_script, run

        attach_script(CLIENT, experiment_id, REF_SCRIPT)
        summary = run(CLIENT, experiment_id, timeout=120)

        # 3 result files created for this experiment
        results_dir = runner_env / "vault" / "clients" / CLIENT / "results"
        result_files = [
            p for p in sorted(results_dir.glob("*.md"))
            if read_markdown(p)[0].get("experiment_id") == experiment_id
        ]
        assert len(result_files) == 3, f"Expected 3 result files, got {[p.name for p in result_files]}"

        # Exactly one result marked winner: true
        winner_flags = [read_markdown(p)[0]["winner"] for p in result_files]
        assert winner_flags.count("true") == 1, f"Expected exactly one winner, got {winner_flags}"

        # Experiment frontmatter status is complete
        exp_path = runner_env / "vault" / "clients" / CLIENT / "experiments" / f"{experiment_id}.md"
        fm, _ = read_markdown(exp_path)
        assert fm["status"] == "complete"

        # Run log file exists
        assert summary["log_path"].exists(), f"Run log missing: {summary['log_path']}"


# ---------------------------------------------------------------------------
# TEST 3 — Runner error handling
# ---------------------------------------------------------------------------

class TestRunnerErrors:

    def test_run_without_script_raises_value_error(self, runner_env, experiment_id):
        """run() must raise ValueError when the experiment has no attached script."""
        from engine.runner import run
        with pytest.raises(ValueError, match="no attached script"):
            run(CLIENT, experiment_id)

    def test_attach_script_missing_path_raises(self, runner_env, experiment_id):
        """attach_script() must raise FileNotFoundError for a nonexistent script."""
        from engine.runner import attach_script
        with pytest.raises(FileNotFoundError):
            attach_script(CLIENT, experiment_id, runner_env / "does-not-exist.py")

"""
tests/test_ask.py — Tests for `sera ask`, the question-to-evidence command.

NO real API calls: hypothesis generation uses the built-in offline fallback
(API key cleared), and engine.scriptgen.generate_script is replaced with a
canned fake — the same boundary-mocking approach test_scriptgen.py uses for
the Anthropic client.

Covers:
    - e2e ask with 3 hypotheses where one fails after repairs → exit 0,
      2 results + 1 FAILED in the table.
    - all hypotheses fail → command errors with a clear message.
    - --client vault reuse: brief ids increment, nothing clobbered.

Run with:
    python -m pytest tests/test_ask.py -v
"""

import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.file_io import ensure_dir, read_markdown


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

CLIENT = "test-ask"
QUESTION = "Which caching strategy has the best hit rate?"


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
def ask_env(tmp_path, monkeypatch):
    """
    Isolated ask environment: patches PROJECT_ROOT + CONFIG everywhere the
    ask pipeline reaches. API key cleared so hypothesis generation uses the
    offline fallback (scriptgen itself is faked per-test).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import shared.config
    import engine.hypothesis
    import engine.experiment
    import engine.results
    import engine.winner
    import engine.runner
    import engine.scriptgen
    import cli.commands.ask

    for mod in (
        shared.config,
        engine.hypothesis,
        engine.experiment,
        engine.results,
        engine.winner,
        engine.runner,
        engine.scriptgen,
        cli.commands.ask,
    ):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONFIG", _TEST_CONFIG)

    return tmp_path


def _fake_summary(tmp_path, client, experiment_id, value, mode="simulation", attempts=1):
    """A generate_script return dict shaped like the real one."""
    log_path = tmp_path / "engine" / "logs" / client / f"run-{experiment_id}-001.log"
    ensure_dir(log_path.parent)
    log_path.write_text("stub run log", encoding="utf-8")
    return {
        "experiment_id": experiment_id,
        "metric": "hit_rate",
        "conditions": {"baseline": round(value - 0.1, 4), "treatment": value},
        "result_ids": [],
        "winner": {
            "winner_id": f"res-{experiment_id}-treatment",
            "winner_condition": "treatment",
            "winner_metric": "hit_rate",
            "winner_value": value,
            "experiment_id": experiment_id,
            "total_results": 2,
        },
        "log_path": log_path,
        "exit_code": 0,
        "attempts": attempts,
        "mode": mode,
    }


def install_fake_scriptgen(monkeypatch, tmp_path, outcomes):
    """
    Replace engine.scriptgen.generate_script with a fake that consumes
    `outcomes` in call order: a float becomes a successful summary with that
    winner value; an Exception instance is raised (a failure after repairs).
    """
    import engine.scriptgen

    state = {"calls": 0}

    def fake_generate_script(client, experiment_id, max_repair_attempts=2,
                             and_run=True, timeout=300):
        outcome = outcomes[state["calls"]]
        state["calls"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return _fake_summary(tmp_path, client, experiment_id, outcome)

    monkeypatch.setattr(engine.scriptgen, "generate_script", fake_generate_script)
    return state


def _invoke_ask(*args):
    from cli.main import sera
    return CliRunner().invoke(sera, ["ask", *args])


# ---------------------------------------------------------------------------
# TEST 1 — e2e with one failing hypothesis
# ---------------------------------------------------------------------------

class TestAskEndToEnd:

    def test_one_failure_still_succeeds(self, ask_env, monkeypatch):
        """3 hypotheses, middle one fails after repairs → exit 0, 2 ok + 1 FAILED."""
        install_fake_scriptgen(monkeypatch, ask_env, [
            0.7,
            RuntimeError("[SERA ScriptGen] Could not produce a working script"),
            0.9,
        ])

        result = _invoke_ask(QUESTION, "--client", CLIENT, "--no-report")

        assert result.exit_code == 0, result.output
        assert "ANSWER" in result.output
        assert "0.9" in result.output  # best winner value surfaced
        assert "2/3 experiments succeeded" in result.output
        assert result.output.count("FAILED") >= 1
        # honest simulation disclosure
        assert "simulated experiments" in result.output

    def test_artifacts_created(self, ask_env, monkeypatch):
        """ask must leave a brief, hypotheses, and experiments in the vault."""
        install_fake_scriptgen(monkeypatch, ask_env, [0.5, 0.6, 0.7])

        result = _invoke_ask(QUESTION, "--client", CLIENT, "--no-report")
        assert result.exit_code == 0, result.output

        client_root = ask_env / "vault" / "clients" / CLIENT
        assert (client_root / "briefs" / "brief-001.md").exists()
        assert len(list((client_root / "hypotheses").glob("hyp-*.md"))) == 3
        assert len(list((client_root / "experiments").glob("exp-*.md"))) == 3


# ---------------------------------------------------------------------------
# TEST 2 — all hypotheses fail
# ---------------------------------------------------------------------------

class TestAskAllFail:

    def test_all_failures_error_out(self, ask_env, monkeypatch):
        """If every experiment fails, the command must error with a clear message."""
        install_fake_scriptgen(monkeypatch, ask_env, [
            RuntimeError("broken 1"),
            RuntimeError("broken 2"),
            RuntimeError("broken 3"),
        ])

        result = _invoke_ask(QUESTION, "--client", CLIENT, "--no-report")

        assert result.exit_code != 0
        assert "All 3 experiments failed" in result.output


# ---------------------------------------------------------------------------
# TEST 3 — client vault reuse
# ---------------------------------------------------------------------------

class TestAskClientReuse:

    def test_second_ask_increments_brief_ids(self, ask_env, monkeypatch):
        """A second ask into the same client must not clobber existing briefs."""
        install_fake_scriptgen(monkeypatch, ask_env, [0.5] * 6)

        first = _invoke_ask(QUESTION, "--client", CLIENT, "--no-report")
        assert first.exit_code == 0, first.output

        briefs_dir = ask_env / "vault" / "clients" / CLIENT / "briefs"
        original = (briefs_dir / "brief-001.md").read_text(encoding="utf-8")

        second_question = "Does prefetching improve the cache hit rate further?"
        second = _invoke_ask(second_question, "--client", CLIENT, "--no-report")
        assert second.exit_code == 0, second.output
        assert "Reusing client vault" in second.output

        assert (briefs_dir / "brief-001.md").exists()
        assert (briefs_dir / "brief-002.md").exists()
        # first brief untouched
        assert (briefs_dir / "brief-001.md").read_text(encoding="utf-8") == original
        fm, _ = read_markdown(briefs_dir / "brief-002.md")
        assert fm["title"] == second_question

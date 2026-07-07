"""
tests/test_memory.py — Tests for SERA's research memory (P4).

NO real API calls: where hypothesis generation needs Claude, a fake
`anthropic` module is installed in sys.modules (same approach as
test_scriptgen.py) so the exact prompt payload can be inspected.

Covers:
    a. ledger record / query relevance ordering / stats math
    b. verdict computation (survived / killed / failed)
    c. memory=True injects past outcomes into the generation prompt;
       memory=False injects nothing — asserted on the mocked payload,
       plus the hypgen audit log
    d. ANSWER condition vote: majority beats a higher raw value; tie-break
       by mean normalized margin
    e. validate_script rejects metrics named neg_*

Run with:
    python -m pytest tests/test_memory.py -v
"""

import json
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
        "vault_root": "vault/",
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

CLIENT = "test-memory"
BRIEF_ID = "brief-001"


def _entry(question, verdict="killed", client=CLIENT, predicted="a", actual="b", title=""):
    return {
        "ts": "2026-07-07T00:00:00",
        "client": client,
        "brief_id": "brief-001",
        "question": question,
        "hypothesis_id": "hyp-001",
        "hypothesis_title": title or question,
        "predicted_winner": predicted,
        "actual_winner": actual,
        "verdict": verdict,
        "metric": "accuracy",
        "winner_value": 0.9,
        "conditions": {"a": 0.5, "b": 0.9},
        "mode": "simulation",
        "attempts": 1,
    }


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
def memory_env(tmp_path, monkeypatch):
    """Isolated env: PROJECT_ROOT + CONFIG patched in ledger + hypothesis."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import shared.config
    import engine.hypothesis
    import engine.ledger

    for mod in (shared.config, engine.hypothesis, engine.ledger):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONFIG", _TEST_CONFIG)

    client_root = tmp_path / "vault" / "clients" / CLIENT
    for sub in ("briefs", "hypotheses", "experiments", "results"):
        ensure_dir(client_root / sub)

    write_markdown(
        client_root / "briefs" / f"{BRIEF_ID}.md",
        body="# Research Brief: Cache strategy\n\n## Objective\n\nWhich caching strategy has the best hit rate?\n",
        frontmatter={
            "title": "Which caching strategy has the best hit rate?",
            "client_id": CLIENT,
            "status": "active",
            "created": "2026-07-07",
        },
    )
    return tmp_path


def install_fake_anthropic_capture(monkeypatch):
    """
    Fake `anthropic` module that captures every prompt and returns a valid
    3-hypothesis JSON response. Returns the capture dict.
    """
    captured = {"prompts": []}
    response = json.dumps([
        {
            "title": f"Hypothesis {i}",
            "hypothesis": "If X, then Y, because Z.",
            "rationale": "Because reasons.",
            "metrics": ["m1", "m2"],
            "predicted_winner": f"condition_{i}",
        }
        for i in (1, 2, 3)
    ])

    def _create(**kwargs):
        captured["prompts"].append(kwargs["messages"][0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(text=response)])

    class Anthropic:
        def __init__(self, api_key=None):
            self.messages = SimpleNamespace(create=_create)

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return captured


# ---------------------------------------------------------------------------
# TEST a — ledger record / query / stats
# ---------------------------------------------------------------------------

class TestLedger:

    def test_record_appends_jsonl(self, memory_env):
        from engine import ledger
        ledger.record(_entry("q one"))
        ledger.record(_entry("q two"))
        lines = (memory_env / "vault" / "ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["question"] == "q one"

    def test_query_orders_by_relevance(self, memory_env):
        from engine import ledger
        ledger.record(_entry("retry backoff strategy wait time"))
        ledger.record(_entry("caching strategy hit rate eviction"))
        ledger.record(_entry("json parsing speed small payloads"))

        results = ledger.query("Which caching strategy maximizes hit rate?")
        assert results, "expected at least one relevant entry"
        assert results[0]["question"] == "caching strategy hit rate eviction"
        # zero-overlap entries never come back
        assert all("json parsing" not in r["question"] for r in results)

    def test_query_respects_k(self, memory_env):
        from engine import ledger
        for i in range(8):
            ledger.record(_entry(f"caching strategy variant {i}"))
        assert len(ledger.query("caching strategy", k=5)) == 5

    def test_stats_math(self, memory_env):
        from engine import ledger
        ledger.record(_entry("q1", verdict="survived", client="alpha"))
        ledger.record(_entry("q2", verdict="killed", client="alpha"))
        ledger.record(_entry("q3", verdict="killed", client="beta"))
        ledger.record(_entry("q4", verdict="failed", client="beta"))

        s = ledger.stats()
        assert s["total"] == 4
        assert (s["survived"], s["killed"], s["failed"]) == (1, 2, 1)
        # failures are excluded from the survival rate denominator
        assert s["survival_rate"] == pytest.approx(1 / 3, abs=1e-4)
        assert s["by_client"] == {"alpha": 2, "beta": 2}

    def test_stats_empty_ledger(self, memory_env):
        from engine import ledger
        s = ledger.stats()
        assert s["total"] == 0
        assert s["survival_rate"] == 0.0


# ---------------------------------------------------------------------------
# TEST b — verdict computation
# ---------------------------------------------------------------------------

class TestVerdict:

    def test_survived_case_insensitive(self):
        from engine.ledger import compute_verdict
        assert compute_verdict("Fixed", "fixed") == "survived"

    def test_killed_on_mismatch(self):
        from engine.ledger import compute_verdict
        assert compute_verdict("exponential_jitter", "fixed") == "killed"

    def test_failed_on_missing_actual(self):
        from engine.ledger import compute_verdict
        assert compute_verdict("fixed", None) == "failed"
        assert compute_verdict("fixed", "") == "failed"


# ---------------------------------------------------------------------------
# TEST c — memory injection into the generation prompt
# ---------------------------------------------------------------------------

class TestMemoryInjection:

    def test_memory_true_injects_past_outcomes(self, memory_env, monkeypatch):
        from engine import ledger
        from engine.hypothesis import generate

        ledger.record(_entry(
            "Which caching strategy has the best hit rate?",
            predicted="lru", actual="lfu", verdict="killed",
        ))

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        captured = install_fake_anthropic_capture(monkeypatch)

        generate(CLIENT, BRIEF_ID, memory=True)

        assert len(captured["prompts"]) == 1
        prompt = captured["prompts"][0]
        assert "PAST RESEARCH OUTCOMES" in prompt
        assert "predicted: lru" in prompt
        assert "actual winner: lfu" in prompt
        assert "verdict: killed" in prompt

        # auditable: hypgen log records the exact injected block
        log = next((memory_env / "engine" / "logs" / CLIENT).glob("hypgen-*.log"))
        assert "PAST RESEARCH OUTCOMES" in log.read_text(encoding="utf-8")

    def test_memory_false_injects_nothing(self, memory_env, monkeypatch):
        from engine import ledger
        from engine.hypothesis import generate

        ledger.record(_entry("Which caching strategy has the best hit rate?"))

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        captured = install_fake_anthropic_capture(monkeypatch)

        generate(CLIENT, BRIEF_ID, memory=False)

        assert "PAST RESEARCH OUTCOMES" not in captured["prompts"][0]
        log = next((memory_env / "engine" / "logs" / CLIENT).glob("hypgen-*.log"))
        assert "none" in log.read_text(encoding="utf-8")

    def test_hypothesis_files_carry_predicted_winner(self, memory_env):
        """Even the offline fallback must stamp predicted_winner frontmatter."""
        from engine.hypothesis import generate
        hyp_ids = generate(CLIENT, BRIEF_ID)  # no API key → fallback
        hyp_dir = memory_env / "vault" / "clients" / CLIENT / "hypotheses"
        for hyp_id in hyp_ids:
            fm, _ = read_markdown(hyp_dir / f"{hyp_id}.md")
            assert fm.get("predicted_winner"), f"{hyp_id} missing predicted_winner"


# ---------------------------------------------------------------------------
# TEST d — ANSWER condition vote
# ---------------------------------------------------------------------------

def _vote_row(winner, conditions):
    return {
        "status": "ok",
        "summary": {
            "metric": "m",
            "conditions": conditions,
            "winner": {"winner_condition": winner, "winner_value": max(conditions.values())},
        },
    }


class TestConditionVote:

    def test_majority_beats_higher_raw_value(self):
        """2-of-3 vote wins even when the single win has a huge raw value."""
        from cli.commands.ask import _condition_vote
        rows = [
            _vote_row("fixed", {"fixed": 0.6, "linear": 0.5}),
            _vote_row("fixed", {"fixed": 0.7, "linear": 0.6}),
            _vote_row("linear", {"linear": 9999.0, "fixed": 1.0}),
        ]
        label, wins, _ = _condition_vote(rows)
        assert label == "fixed"
        assert wins == 2

    def test_vote_is_case_insensitive(self):
        from cli.commands.ask import _condition_vote
        rows = [
            _vote_row("Fixed", {"Fixed": 0.6, "linear": 0.5}),
            _vote_row("fixed", {"fixed": 0.7, "linear": 0.6}),
            _vote_row("linear", {"linear": 0.9, "fixed": 0.1}),
        ]
        label, wins, _ = _condition_vote(rows)
        assert label.lower() == "fixed"
        assert wins == 2

    def test_tie_breaks_on_mean_normalized_margin(self):
        """1-1 tie → the condition that won by the wider normalized margin."""
        from cli.commands.ask import _condition_vote
        rows = [
            # 'a' wins narrowly: margin (10-9.5)/(10-1) ≈ 0.056
            _vote_row("a", {"a": 10.0, "b": 9.5, "c": 1.0}),
            # 'b' wins decisively: margin (0.9-0.2)/(0.9-0.1) = 0.875
            _vote_row("b", {"b": 0.9, "a": 0.2, "c": 0.1}),
        ]
        label, wins, margin = _condition_vote(rows)
        assert label == "b"
        assert wins == 1
        assert margin == pytest.approx(0.875, abs=1e-4)


# ---------------------------------------------------------------------------
# TEST e — neg_* metric rejection
# ---------------------------------------------------------------------------

class TestNegMetricRejected:

    def test_rejects_negated_metric_name(self):
        from engine.scriptgen import validate_script
        code = (
            "import json\n"
            'print("SERA_METRICS " + json.dumps('
            '{"metric": "neg_mean_wait_ms", "conditions": {"a": -1.0, "b": -2.0}}))\n'
        )
        violations = validate_script(code)
        assert any("neg_mean_wait_ms" in v for v in violations)

    def test_accepts_transformed_metric_name(self):
        from engine.scriptgen import validate_script
        code = (
            "import json\n"
            'print("SERA_METRICS " + json.dumps('
            '{"metric": "success_rate_per_wait_s", "conditions": {"a": 1.0, "b": 2.0}}))\n'
        )
        assert validate_script(code) == []

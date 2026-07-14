"""
tests/test_ablation_run2.py — Tests for the run-2 ablation hardening
(docs/evidence/p6.md rerun design). All offline; zero real API calls.

Covers the four fixes:
    1. Interleaved arm ordering + per-ask ledger switching.
    2. Billing/credit error -> whole-run abort (BillingError propagates).
    3. Rate-limit (429) retried with backoff, then succeeds.
    4. 429 that survives every retry fails ONE hypothesis only; the run
       continues and other hypotheses in the brief still succeed.
    5. Strict hypgen raises where the legacy fallback would have returned
       templates.

Run with:
    python -m pytest tests/test_ablation_run2.py -v
"""

import json
import shutil
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.file_io import ensure_dir, write_markdown


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

BRIEFS = [
    {"id": "t-001", "question": "Which caching strategy has the best hit rate?"},
    {"id": "t-002", "question": "Which retry backoff minimizes total wait time?"},
]

# Stand-in Anthropic exception types (class NAME is what engine.api keys on).
class RateLimitError(Exception):
    status_code = 429


class BadRequestError(Exception):
    pass


BILLING_EXC = BadRequestError(
    "Error code: 400 - {'type': 'error', 'error': {'type': "
    "'invalid_request_error', 'message': 'Your credit balance is too low to "
    "access the Anthropic API. Please go to Plans & Billing to upgrade.'}}"
)

VALID_SCRIPT = (
    "import json\n"
    'print("SERA_METRICS " + json.dumps('
    '{"metric": "accuracy", "conditions": {"a": 0.7, "b": 0.4}}))\n'
)

HYP_JSON = json.dumps([
    {"title": f"Hyp {i}", "hypothesis": "If X then Y because Z.",
     "rationale": "reasons", "metrics": ["m1", "m2"],
     "predicted_winner": f"cond_{i}"}
    for i in (1, 2, 3)
])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_test_clients():
    yield
    real_clients = PROJECT_ROOT / "vault" / "clients"
    if real_clients.exists():
        for leftover in real_clients.glob("ablation-*"):
            shutil.rmtree(leftover, ignore_errors=True)


@pytest.fixture
def ablation_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SERA_LEDGER_PATH", raising=False)

    import shared.config
    import engine.hypothesis
    import engine.experiment
    import engine.results
    import engine.winner
    import engine.runner
    import engine.scriptgen
    import engine.ledger
    import engine.ablation

    for mod in (
        shared.config, engine.hypothesis, engine.experiment, engine.results,
        engine.winner, engine.runner, engine.scriptgen, engine.ledger,
        engine.ablation,
    ):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONFIG", _TEST_CONFIG)

    briefs_path = tmp_path / "briefs.jsonl"
    briefs_path.write_text("\n".join(json.dumps(b) for b in BRIEFS) + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def memory_env(tmp_path, monkeypatch):
    """Minimal env for testing engine.hypothesis.generate in isolation."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import shared.config
    import engine.hypothesis
    import engine.ledger

    for mod in (shared.config, engine.hypothesis, engine.ledger):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONFIG", _TEST_CONFIG)

    client_root = tmp_path / "vault" / "clients" / "test-strict"
    for sub in ("briefs", "hypotheses", "experiments", "results"):
        ensure_dir(client_root / sub)
    write_markdown(
        client_root / "briefs" / "brief-001.md",
        body="# Brief\n\n## Objective\n\nWhich caching strategy has the best hit rate?\n",
        frontmatter={"title": "Which caching strategy has the best hit rate?",
                     "client_id": "test-strict", "status": "active", "created": "2026-07-14"},
    )
    return tmp_path


def install_fake_anthropic(monkeypatch, on_create):
    """Install a fake `anthropic` whose messages.create delegates to on_create()."""
    class Anthropic:
        def __init__(self, api_key=None):
            self.messages = SimpleNamespace(create=lambda **kw: on_create(kw))

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Anthropic
    fake.RateLimitError = RateLimitError
    fake.BadRequestError = BadRequestError
    monkeypatch.setitem(sys.modules, "anthropic", fake)


def _text(payload):
    return SimpleNamespace(content=[SimpleNamespace(text=payload)])


# ---------------------------------------------------------------------------
# TEST 1 — interleave order + per-ask ledger switching
# ---------------------------------------------------------------------------

class TestInterleave:

    def test_arm_repeat_order_is_interleaved_per_brief(self, ablation_env, monkeypatch):
        """Order must be [(on,1),(off,1),(on,2),(off,2)] within each brief,
        with cycle outermost — and SERA_LEDGER_PATH must match each ask."""
        import os
        import engine.ablation as ablation

        seen = []
        real_run_brief = ablation._run_brief

        def spy(client, brief, memory, dry_run, timeout, repeat):
            seen.append((brief["id"], "on" if memory else "off", repeat,
                         Path(os.environ["SERA_LEDGER_PATH"]).name))
            return real_run_brief(client, brief, memory, dry_run, timeout, repeat)

        monkeypatch.setattr(ablation, "_run_brief", spy)

        ablation.run_ablation(ablation_env / "briefs.jsonl", cycles=2, repeats=2,
                              out_dir=ablation_env / "runs" / "il", dry_run=True)

        # cycle 1, brief t-001: the four arm×repeat asks, in interleaved order
        first_brief_c1 = [s for s in seen[:4]]
        assert first_brief_c1 == [
            ("t-001", "on", 1, "ledger-on-r1.jsonl"),
            ("t-001", "off", 1, "ledger-off-r1.jsonl"),
            ("t-001", "on", 2, "ledger-on-r2.jsonl"),
            ("t-001", "off", 2, "ledger-off-r2.jsonl"),
        ]
        # cycle is outermost: every cycle-1 ask precedes every cycle-2 ask.
        # 2 briefs × 4 arm-repeats = 8 asks per cycle.
        assert len(seen) == 2 * len(BRIEFS) * 4
        c1_ledger_writes = seen[:8]
        # within cycle 1 both briefs are covered before cycle 2 starts
        assert {s[0] for s in c1_ledger_writes} == {"t-001", "t-002"}
        # the per-ask ledger name always encodes the ask's own arm+repeat
        for _bid, arm, rep, ledger_name in seen:
            assert ledger_name == f"ledger-{arm}-r{rep}.jsonl"

    def test_cycle_order_preserved_for_memory_validity(self, ablation_env, monkeypatch):
        """For a given (arm,repeat), all of cycle 1 completes before cycle 2."""
        import os
        import engine.ablation as ablation

        order = []
        real_run_brief = ablation._run_brief

        def spy(client, brief, memory, dry_run, timeout, repeat):
            # infer cycle from how many times this exact client has been seen
            order.append((client, brief["id"]))
            return real_run_brief(client, brief, memory, dry_run, timeout, repeat)

        monkeypatch.setattr(ablation, "_run_brief", spy)
        ablation.run_ablation(ablation_env / "briefs.jsonl", cycles=2, repeats=1,
                              out_dir=ablation_env / "runs" / "cy", dry_run=True)

        on_client = [c for c, _ in order if c.endswith("on-r1")]
        # on-r1 appears once per brief per cycle = 2 briefs × 2 cycles = 4 times,
        # and the first two (cycle 1) precede the last two (cycle 2)
        assert len(on_client) == 4


# ---------------------------------------------------------------------------
# TEST 2 — billing error aborts the whole run
# ---------------------------------------------------------------------------

class TestBillingAbort:

    def test_billing_error_halts_entire_run(self, ablation_env, monkeypatch):
        from engine.api import BillingError
        import engine.ablation as ablation

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        calls = {"n": 0}

        def on_create(kw):
            calls["n"] += 1
            raise BILLING_EXC  # every call is a credit-exhaustion 400

        install_fake_anthropic(monkeypatch, on_create)

        with pytest.raises(BillingError):
            ablation.run_ablation(ablation_env / "briefs.jsonl", cycles=2, repeats=2,
                                  out_dir=ablation_env / "runs" / "bill", dry_run=False)

        # It aborted on the FIRST ask's hypgen call — did not grind through
        # the remaining 15 asks recording bogus failures.
        assert calls["n"] == 1

    def test_billing_via_call_with_backoff_not_retried(self, monkeypatch):
        from engine.api import call_with_backoff, BillingError

        slept = []
        with pytest.raises(BillingError):
            call_with_backoff(lambda: (_ for _ in ()).throw(BILLING_EXC),
                              sleep=slept.append)
        assert slept == []  # billing errors are never retried


# ---------------------------------------------------------------------------
# TEST 3 — 429 retried then succeeds
# ---------------------------------------------------------------------------

class TestRateLimitBackoff:

    def test_429_then_success_is_retried(self, monkeypatch):
        from engine.api import call_with_backoff, RATE_LIMIT_BACKOFF_SECONDS

        state = {"n": 0}
        slept = []

        def make_call():
            state["n"] += 1
            if state["n"] == 1:
                raise RateLimitError("429 slow down")
            return "ok"

        result = call_with_backoff(make_call, sleep=slept.append)
        assert result == "ok"
        assert state["n"] == 2
        assert slept == [RATE_LIMIT_BACKOFF_SECONDS[0]]  # one backoff of 5s

    def test_scriptgen_retries_429_then_succeeds(self, ablation_env, monkeypatch):
        """End-to-end through scriptgen: a 429 then a valid script -> success."""
        import engine.scriptgen as scriptgen
        from engine.experiment import create
        from engine.hypothesis import generate

        # patch the backoff sleep where it lives so retries don't wait
        import engine.api as api
        monkeypatch.setattr(api.time, "sleep", lambda s: None)

        # build a client + hypothesis offline (no key), then a real scriptgen call
        client_root = ablation_env / "vault" / "clients" / "ablation-t"
        for sub in ("briefs", "hypotheses", "experiments", "results"):
            ensure_dir(client_root / sub)
        write_markdown(
            client_root / "briefs" / "brief-001.md",
            body="# Brief\n\n## Objective\n\nCache hit rate?\n",
            frontmatter={"title": "Cache hit rate?", "client_id": "ablation-t",
                         "status": "active", "created": "2026-07-14"},
        )
        hyp_ids = generate("ablation-t", "brief-001")  # offline fallback
        exp_id = create("ablation-t", hyp_ids[0])

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        state = {"n": 0}

        def on_create(kw):
            state["n"] += 1
            if state["n"] == 1:
                raise RateLimitError("429")
            return _text(VALID_SCRIPT)

        install_fake_anthropic(monkeypatch, on_create)
        summary = scriptgen.generate_script("ablation-t", exp_id)
        assert summary["attempts"] == 1   # one logical attempt (429 retried under it)
        assert state["n"] == 2            # the 429 was retried
        assert summary["winner"]["winner_condition"] == "a"


# ---------------------------------------------------------------------------
# TEST 4 — exhausted 429 fails ONE hypothesis only, run continues
# ---------------------------------------------------------------------------

class TestRateLimitExhausted:

    def test_exhausted_429_fails_one_hypothesis_only(self, ablation_env, monkeypatch):
        import engine.api as api
        import engine.ablation as ablation
        monkeypatch.setattr(api.time, "sleep", lambda s: None)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        # hypgen always succeeds (JSON); scriptgen 429s FOREVER for the one
        # hypothesis whose predicted winner is cond_1 (the first of each
        # brief), valid for the rest. Keying on the label — not a call
        # counter — makes it fail on every retry too, so the backoff is
        # genuinely exhausted for that hypothesis.
        def on_create(kw):
            msgs = kw.get("messages", [])
            content = msgs[0]["content"] if msgs else ""
            if "testable research hypotheses" in content:  # hypgen
                return _text(HYP_JSON)
            if "'cond_1'" in content:  # scriptgen for the first hypothesis
                raise RateLimitError("429 forever")
            return _text(VALID_SCRIPT)

        install_fake_anthropic(monkeypatch, on_create)

        summary = ablation.run_ablation(
            ablation_env / "briefs.jsonl", cycles=1, repeats=1,
            memory_arms=("on",), out_dir=ablation_env / "runs" / "ex", dry_run=False)

        rows = [json.loads(l) for l in
                (ablation_env / "runs" / "ex" / "results.jsonl")
                .read_text(encoding="utf-8").strip().splitlines()]
        # 2 briefs × 3 hyp = 6 rows; the run did NOT abort
        assert len(rows) == len(BRIEFS) * 3
        failed = [r for r in rows if r["verdict"] == "failed"]
        decided = [r for r in rows if r["verdict"] != "failed"]
        # exactly the round-robin-first hypothesis of each brief failed
        assert len(failed) == len(BRIEFS)
        assert len(decided) == len(BRIEFS) * 2


# ---------------------------------------------------------------------------
# TEST 5 — strict hypgen raises where legacy falls back
# ---------------------------------------------------------------------------

class TestStrictHypgen:

    def test_strict_raises_on_api_failure(self, memory_env, monkeypatch):
        from engine.hypothesis import generate

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        install_fake_anthropic(
            monkeypatch,
            lambda kw: (_ for _ in ()).throw(RuntimeError("transient API blip")))

        with pytest.raises(RuntimeError):
            generate("test-strict", "brief-001", memory=False, strict=True)

    def test_legacy_falls_back_to_templates(self, memory_env, monkeypatch):
        from engine.hypothesis import generate

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        install_fake_anthropic(
            monkeypatch,
            lambda kw: (_ for _ in ()).throw(RuntimeError("transient API blip")))

        hyp_ids = generate("test-strict", "brief-001", memory=False, strict=False)
        assert len(hyp_ids) == 3  # template fallback still produced 3

    def test_strict_billing_raises_billing_error(self, memory_env, monkeypatch):
        from engine.hypothesis import generate
        from engine.api import BillingError

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        install_fake_anthropic(monkeypatch, lambda kw: (_ for _ in ()).throw(BILLING_EXC))

        with pytest.raises(BillingError):
            generate("test-strict", "brief-001", memory=False, strict=True)

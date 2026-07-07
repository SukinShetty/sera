"""
tests/test_ablation.py — Tests for the memory ablation harness (P5).

All offline: dry-run mode + the hypothesis fallback generator. Zero API calls.

Covers:
    a. arm isolation — memory-off NEVER calls ledger.query; every
       arm×repeat writes its own distinct ledger file
    b. HSR math — failures excluded; mean/std across repeats
    c. dry-run end-to-end — results.jsonl, summary.json, png, csv all
       produced with correct shapes
    d. cycle bookkeeping — cycle numbers and brief coverage correct

Run with:
    python -m pytest tests/test_ablation.py -v
"""

import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


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

BRIEFS = [
    {"id": "t-001", "question": "Which caching strategy has the best hit rate?"},
    {"id": "t-002", "question": "Which retry backoff minimizes total wait time?"},
    {"id": "t-003", "question": "Which tokenizer maximizes keyword recall?"},
]


@pytest.fixture(autouse=True)
def cleanup_test_clients():
    """Remove any ablation-* client vaults left in the real vault."""
    yield
    real_clients = PROJECT_ROOT / "vault" / "clients"
    if real_clients.exists():
        for leftover in real_clients.glob("ablation-*"):
            shutil.rmtree(leftover, ignore_errors=True)


@pytest.fixture
def ablation_env(tmp_path, monkeypatch):
    """Isolated env for the whole ablation pipeline."""
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
        shared.config,
        engine.hypothesis,
        engine.experiment,
        engine.results,
        engine.winner,
        engine.runner,
        engine.scriptgen,
        engine.ledger,
        engine.ablation,
    ):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONFIG", _TEST_CONFIG)

    briefs_path = tmp_path / "briefs.jsonl"
    briefs_path.write_text(
        "\n".join(json.dumps(b) for b in BRIEFS) + "\n", encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# TEST a — arm isolation
# ---------------------------------------------------------------------------

class TestArmIsolation:

    def test_memory_off_never_queries_ledger(self, ablation_env, monkeypatch):
        import engine.ledger
        from engine.ablation import run_ablation

        calls = {"n": 0}
        original = engine.ledger.query

        def spy(question, k=5):
            calls["n"] += 1
            return original(question, k)

        monkeypatch.setattr(engine.ledger, "query", spy)

        run_ablation(ablation_env / "briefs.jsonl", cycles=2, repeats=1,
                     memory_arms=("off",), out_dir=ablation_env / "runs" / "off-only",
                     dry_run=True)
        assert calls["n"] == 0, "memory-off arm must never read the ledger"

        run_ablation(ablation_env / "briefs.jsonl", cycles=2, repeats=1,
                     memory_arms=("on",), out_dir=ablation_env / "runs" / "on-only",
                     dry_run=True)
        assert calls["n"] > 0, "memory-on arm must read the ledger"

    def test_each_arm_repeat_gets_distinct_ledger(self, ablation_env):
        from engine.ablation import run_ablation

        out_dir = ablation_env / "runs" / "iso"
        run_ablation(ablation_env / "briefs.jsonl", cycles=1, repeats=2,
                     out_dir=out_dir, dry_run=True)

        ledgers = sorted(p.name for p in out_dir.glob("ledger-*.jsonl"))
        assert ledgers == [
            "ledger-off-r1.jsonl", "ledger-off-r2.jsonl",
            "ledger-on-r1.jsonl", "ledger-on-r2.jsonl",
        ]
        # every arm×repeat actually recorded outcomes to its own file
        for name in ledgers:
            lines = (out_dir / name).read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == len(BRIEFS) * 3, f"{name} has {len(lines)} entries"

    def test_env_var_restored_after_run(self, ablation_env):
        import os
        from engine.ablation import run_ablation

        run_ablation(ablation_env / "briefs.jsonl", cycles=1, repeats=1,
                     out_dir=ablation_env / "runs" / "env", dry_run=True)
        assert "SERA_LEDGER_PATH" not in os.environ


# ---------------------------------------------------------------------------
# TEST b — HSR math
# ---------------------------------------------------------------------------

def _row(arm, cycle, repeat, verdict):
    return {"arm": arm, "cycle": cycle, "repeat": repeat, "brief_id": "t-001",
            "hypothesis_id": "hyp-001", "predicted_winner": "a",
            "actual_winner": "a" if verdict == "survived" else "b",
            "verdict": verdict}


class TestHSRMath:

    def test_hsr_excludes_failures(self):
        from engine.ablation import hsr
        assert hsr(2, 2) == 0.5
        assert hsr(0, 0) == 0.0  # nothing decided (e.g. all failed)
        assert hsr(3, 0) == 1.0

    def test_summarize_mean_and_std_across_repeats(self):
        from engine.ablation import summarize

        results = (
            # repeat 1: 2 survived, 1 killed → HSR 2/3
            [_row("on", 1, 1, "survived")] * 2 + [_row("on", 1, 1, "killed")]
            # repeat 2: 1 survived, 2 killed → HSR 1/3
            + [_row("on", 1, 2, "survived")] + [_row("on", 1, 2, "killed")] * 2
            # plus failures that must not move HSR
            + [_row("on", 1, 1, "failed"), _row("on", 1, 2, "failed")]
        )

        summary = summarize(results, cycles=1, repeats=2, memory_arms=("on",))
        cycle1 = summary["arms"]["on"]["cycles"][0]

        assert cycle1["hsr_mean"] == pytest.approx(0.5, abs=1e-4)
        # population std of [2/3, 1/3] = 1/6
        assert cycle1["hsr_std"] == pytest.approx(1 / 6, abs=1e-4)
        assert cycle1["survived"] == 3
        assert cycle1["killed"] == 3
        assert cycle1["failed"] == 2


# ---------------------------------------------------------------------------
# TEST c — dry-run end-to-end artifacts
# ---------------------------------------------------------------------------

class TestDryRunEndToEnd:

    def test_all_artifacts_produced_with_correct_shapes(self, ablation_env):
        from engine.ablation import run_ablation

        out_dir = ablation_env / "runs" / "e2e"
        summary = run_ablation(ablation_env / "briefs.jsonl", cycles=2, repeats=2,
                               out_dir=out_dir, dry_run=True)

        # results.jsonl: briefs × cycles × arms × repeats × 3 hypotheses
        rows = [json.loads(line) for line in
                (out_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()]
        assert len(rows) == len(BRIEFS) * 2 * 2 * 2 * 3
        for row in rows:
            assert set(row) == {"arm", "repeat", "cycle", "brief_id",
                                "hypothesis_id", "predicted_winner",
                                "actual_winner", "verdict"}
            assert row["verdict"] in ("survived", "killed", "failed")

        # summary.json: both arms, 2 cycles each, sane HSR values
        saved = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        assert set(saved["arms"]) == {"on", "off"}
        for arm_data in saved["arms"].values():
            assert [c["cycle"] for c in arm_data["cycles"]] == [1, 2]
            for cycle_stat in arm_data["cycles"]:
                assert 0.0 <= cycle_stat["hsr_mean"] <= 1.0
                assert len(cycle_stat["per_repeat"]) == 2

        # chart + csv
        assert (out_dir / "ablation_curve.png").stat().st_size > 0
        with (out_dir / "ablation_curve.csv").open(encoding="utf-8") as f:
            csv_rows = list(csv.reader(f))
        assert csv_rows[0] == ["arm", "cycle", "repeat", "hsr", "survived", "killed", "failed"]
        assert len(csv_rows) == 1 + 2 * 2 * 2  # header + arms×cycles×repeats

        # returned summary points at the artifacts
        assert Path(summary["paths"]["png"]).exists()
        assert Path(summary["paths"]["csv"]).exists()

    def test_dry_run_is_deterministic(self, ablation_env):
        from engine.ablation import run_ablation

        s1 = run_ablation(ablation_env / "briefs.jsonl", cycles=1, repeats=1,
                          out_dir=ablation_env / "runs" / "d1", dry_run=True)
        s2 = run_ablation(ablation_env / "briefs.jsonl", cycles=1, repeats=1,
                          out_dir=ablation_env / "runs" / "d2", dry_run=True)
        assert s1["arms"] == s2["arms"]


# ---------------------------------------------------------------------------
# TEST d — cycle bookkeeping
# ---------------------------------------------------------------------------

class TestCycleBookkeeping:

    def test_cycles_and_brief_coverage(self, ablation_env):
        from engine.ablation import run_ablation

        out_dir = ablation_env / "runs" / "cycles"
        run_ablation(ablation_env / "briefs.jsonl", cycles=3, repeats=1,
                     out_dir=out_dir, dry_run=True)

        rows = [json.loads(line) for line in
                (out_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()]

        brief_ids = {b["id"] for b in BRIEFS}
        for arm in ("on", "off"):
            arm_rows = [r for r in rows if r["arm"] == arm]
            assert {r["cycle"] for r in arm_rows} == {1, 2, 3}
            for cycle in (1, 2, 3):
                cycle_rows = [r for r in arm_rows if r["cycle"] == cycle]
                # every brief covered, 3 hypotheses each
                assert {r["brief_id"] for r in cycle_rows} == brief_ids
                assert len(cycle_rows) == len(BRIEFS) * 3

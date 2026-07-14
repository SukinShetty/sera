"""
tests/test_answer_synthesis.py — Tests for metric-aware ANSWER synthesis.

No API calls: _synthesize_answer is pure logic over succeeded-experiment
row dicts (the same shape cli.commands.ask builds from scriptgen summaries).

The bug this guards against: the ANSWER headline crowning an objectively
worse condition because the vote counted experiment WINS and fell to a
margin/alphabetical tiebreak, ignoring that two experiments measured the
SAME commensurable metric.

Covers:
    a. dedup case — two experiments share f1_score (0.2102 fuzzy vs 0.8696
       combined); the answer MUST be combined, never fuzzy.
    b. retry case — 3 different metrics; the honest different-metric vote
       path is used; raw values are never compared across metrics.
    c. degenerate guard — a condition that won its experiment at a lower
       same-metric value than another condition is NOT crowned.
    d. clean shared-metric — highest value on the shared metric wins.

Run with:
    python -m pytest tests/test_answer_synthesis.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.commands.ask import _synthesize_answer, _guard_same_metric


def _row(metric, winner, value, conditions, title="H"):
    """One succeeded-experiment row, matching the shape ask.py builds."""
    return {
        "title": title,
        "status": "ok",
        "summary": {
            "metric": metric,
            "conditions": conditions,
            "winner": {"winner_condition": winner, "winner_value": value},
            "mode": "measurement",
            "attempts": 1,
        },
    }


# ---------------------------------------------------------------------------
# a. dedup case — the real failure that motivated the fix
# ---------------------------------------------------------------------------

class TestDedupCase:

    def test_combined_beats_fuzzy_on_shared_f1(self):
        rows = [
            _row("f1_score", "fuzzy_matching", 0.2102,
                 {"fuzzy_matching": 0.2102, "exact_match": 0.15}, title="Fuzzy"),
            _row("f1_score", "combined_pipeline", 0.8696,
                 {"combined_pipeline": 0.8696, "fuzzy_matching": 0.30}, title="Combined"),
            _row("precision", "exact_match", 0.95,
                 {"exact_match": 0.95, "fuzzy_matching": 0.40}, title="Exact"),
        ]
        answer = _synthesize_answer(rows)
        assert answer["path"] == "shared-metric"
        assert answer["metric"] == "f1_score"
        assert answer["condition"] == "combined_pipeline"
        assert answer["value"] == 0.8696
        assert answer["shared_count"] == 2
        # the objectively worse condition is never crowned
        assert answer["condition"] != "fuzzy_matching"


# ---------------------------------------------------------------------------
# b. retry case — incommensurable metrics, honest vote path
# ---------------------------------------------------------------------------

class TestRetryCase:

    def test_different_metrics_use_honest_vote_path(self):
        rows = [
            _row("recovery_rate", "exponential_jitter", 0.88,
                 {"exponential_jitter": 0.88, "fixed": 0.50}, title="Recovery"),
            _row("efficiency_score", "linear", 0.42,
                 {"linear": 0.42, "fixed": 0.20}, title="Efficiency"),
            _row("sla_compliance", "fixed", 0.99,
                 {"fixed": 0.99, "linear": 0.60}, title="SLA"),
        ]
        answer = _synthesize_answer(rows)
        # metrics all differ -> no shared-metric value crown
        assert answer["path"] == "different-metric"
        assert answer["metric"] is None
        assert answer["value"] is None
        # a real winner of some experiment, decided by wins not raw value
        assert answer["condition"] in {"exponential_jitter", "linear", "fixed"}
        # crucially NOT chosen by max raw value across metrics (that would be
        # sla_compliance's fixed at 0.99); the path forbids that comparison.
        assert answer["wins"] == 1

    def test_does_not_compare_raw_values_across_metrics(self):
        # The globally highest raw value (0.99) belongs to a metric shared by
        # nobody; a value-comparison bug would crown it outright. The honest
        # path must not report a value at all.
        rows = [
            _row("metric_a", "cond_a", 0.10, {"cond_a": 0.10, "z": 0.05}),
            _row("metric_b", "cond_b", 0.99, {"cond_b": 0.99, "y": 0.90}),
            _row("metric_c", "cond_c", 0.50, {"cond_c": 0.50, "x": 0.40}),
        ]
        answer = _synthesize_answer(rows)
        assert answer["path"] == "different-metric"
        assert answer["value"] is None


# ---------------------------------------------------------------------------
# c. degenerate guard — vote path must not crown a beaten same-metric cond
# ---------------------------------------------------------------------------

class TestDegenerateGuard:

    def test_lower_same_metric_winner_is_not_crowned(self):
        # Two metrics tie for most-common (f1 x2, recall x2) -> vote path.
        # The vote's alphabetical tiebreak would otherwise crown "zzz_low"
        # (f1 winner at 0.30) even though "aaa_high" won the other f1
        # experiment at 0.80. The guard must switch to aaa_high.
        rows = [
            _row("f1", "zzz_low", 0.30, {"zzz_low": 0.30, "x": 0.10}, title="E1"),
            _row("f1", "aaa_high", 0.80, {"aaa_high": 0.80, "y": 0.20}, title="E2"),
            _row("recall", "mmm", 0.50, {"mmm": 0.50, "n": 0.40}, title="E3"),
            _row("recall", "kkk", 0.60, {"kkk": 0.60, "p": 0.50}, title="E4"),
        ]
        answer = _synthesize_answer(rows)
        assert answer["path"] == "different-metric"
        assert answer["condition"] == "aaa_high"
        assert answer["condition"] != "zzz_low"

    def test_guard_is_noop_when_no_higher_same_metric_peer(self):
        # zzz_high actually holds the top f1 value -> guard leaves it alone.
        rows = [
            _row("f1", "zzz_high", 0.90, {"zzz_high": 0.90, "x": 0.10}),
            _row("f1", "aaa_low", 0.40, {"aaa_low": 0.40, "y": 0.20}),
            _row("recall", "mmm", 0.50, {"mmm": 0.50, "n": 0.40}),
            _row("recall", "kkk", 0.60, {"kkk": 0.60, "p": 0.50}),
        ]
        # f1 is not uniquely dominant (recall also x2) -> vote path
        assert _guard_same_metric("zzz_high", rows) == "zzz_high"


# ---------------------------------------------------------------------------
# d. clean shared-metric — highest value on the shared metric wins
# ---------------------------------------------------------------------------

class TestCleanSharedMetric:

    def test_highest_value_on_shared_metric_wins(self):
        rows = [
            _row("accuracy", "model_a", 0.60, {"model_a": 0.60, "base": 0.50}),
            _row("accuracy", "model_b", 0.90, {"model_b": 0.90, "base": 0.55}),
            _row("accuracy", "model_c", 0.70, {"model_c": 0.70, "base": 0.52}),
        ]
        answer = _synthesize_answer(rows)
        assert answer["path"] == "shared-metric"
        assert answer["metric"] == "accuracy"
        assert answer["condition"] == "model_b"
        assert answer["value"] == 0.90
        assert answer["shared_count"] == 3

    def test_single_experiment_reports_its_winner(self):
        # one experiment: trivially its own winner, on its own metric
        rows = [_row("accuracy", "only_model", 0.75, {"only_model": 0.75, "base": 0.5})]
        answer = _synthesize_answer(rows)
        # a lone metric is "shared by >=2"? No — count 1. Falls to vote path,
        # which crowns the sole winner. Either way the sole winner is crowned.
        assert answer["condition"] == "only_model"

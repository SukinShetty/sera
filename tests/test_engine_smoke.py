"""
tests/test_engine_smoke.py — Session 3 smoke tests for the SERA Experiment Engine.

Tests cover the four public APIs:
    engine.hypothesis.generate(client, brief_id)
    engine.experiment.create(client, hypothesis_id)
    engine.results.log_result(client, experiment_id, condition, metric, value)
    engine.results.list_results(client, experiment_id)
    engine.winner.select_winner(client, experiment_id)

All tests run in an isolated temp directory (never touch the real vault).
The Anthropic API key is cleared so only the fallback generator is exercised.

Run with:
    python -m pytest tests/test_engine_smoke.py -v
"""

import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.file_io import ensure_dir, write_markdown, read_markdown


# ---------------------------------------------------------------------------
# Shared test configuration
# ---------------------------------------------------------------------------

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

CLIENT = "test-acme"
BRIEF_ID = "brief-001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine_env(tmp_path, monkeypatch):
    """
    Isolated engine environment: patches PROJECT_ROOT + CONFIG in all engine
    modules to point at tmp_path. Creates a minimal client vault with one brief.
    No ANTHROPIC_API_KEY so the fallback generator is used.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import shared.config
    import engine.hypothesis
    import engine.experiment
    import engine.results
    import engine.winner

    for mod in (shared.config, engine.hypothesis, engine.experiment, engine.results, engine.winner):
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
            "# Research Brief: Q1 Growth Drivers\n\n"
            "## Objective\n\nUnderstand what drives trial-to-paid conversion.\n\n"
            "## Research Questions\n\n"
            "1. What friction points stop trial users from converting?\n"
            "2. Which onboarding steps correlate with conversion?\n"
        ),
        frontmatter={
            "title": "Q1 Growth Drivers",
            "client_id": CLIENT,
            "status": "active",
            "created": "2026-05-12",
        },
    )

    return tmp_path


# ---------------------------------------------------------------------------
# TEST 1 — Hypothesis generation
# ---------------------------------------------------------------------------

class TestHypothesisGenerate:

    def test_generate_returns_three_ids(self, engine_env):
        """generate() must return exactly 3 hypothesis IDs."""
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        assert len(ids) == 3, f"Expected 3 hypothesis IDs, got {ids}"

    def test_generate_ids_are_strings_with_prefix(self, engine_env):
        """Each returned ID must be a string starting with 'hyp-'."""
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        for hyp_id in ids:
            assert isinstance(hyp_id, str)
            assert hyp_id.startswith("hyp-"), f"ID {hyp_id!r} does not start with 'hyp-'"

    def test_generate_creates_markdown_files(self, engine_env):
        """Each hypothesis ID must correspond to a .md file in hypotheses/."""
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        hyp_dir = engine_env / "vault" / "clients" / CLIENT / "hypotheses"
        for hyp_id in ids:
            assert (hyp_dir / f"{hyp_id}.md").exists(), f"{hyp_id}.md not found"

    def test_generate_files_have_required_frontmatter(self, engine_env):
        """Each hypothesis file must have the required frontmatter fields."""
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        hyp_dir = engine_env / "vault" / "clients" / CLIENT / "hypotheses"
        required_fields = {"id", "brief_id", "client_id", "title", "status", "created"}
        for hyp_id in ids:
            fm, _ = read_markdown(hyp_dir / f"{hyp_id}.md")
            missing = required_fields - set(fm.keys())
            assert not missing, f"{hyp_id}.md missing frontmatter: {missing}"

    def test_generate_brief_id_matches(self, engine_env):
        """Each hypothesis file must reference the correct brief_id."""
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        hyp_dir = engine_env / "vault" / "clients" / CLIENT / "hypotheses"
        for hyp_id in ids:
            fm, _ = read_markdown(hyp_dir / f"{hyp_id}.md")
            assert fm["brief_id"] == BRIEF_ID

    def test_generate_status_is_draft(self, engine_env):
        """Newly generated hypotheses must have status 'draft'."""
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        hyp_dir = engine_env / "vault" / "clients" / CLIENT / "hypotheses"
        for hyp_id in ids:
            fm, _ = read_markdown(hyp_dir / f"{hyp_id}.md")
            assert fm["status"] == "draft"

    def test_generate_body_contains_hypothesis_heading(self, engine_env):
        """Each hypothesis file body must contain the '# Hypothesis:' heading."""
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        hyp_dir = engine_env / "vault" / "clients" / CLIENT / "hypotheses"
        for hyp_id in ids:
            _, body = read_markdown(hyp_dir / f"{hyp_id}.md")
            assert "# Hypothesis:" in body, f"{hyp_id}.md body missing heading"

    def test_generate_missing_brief_raises_file_not_found(self, engine_env):
        """generate() must raise FileNotFoundError when the brief does not exist."""
        from engine.hypothesis import generate
        with pytest.raises(FileNotFoundError):
            generate(CLIENT, "brief-nonexistent")


# ---------------------------------------------------------------------------
# TEST 2 — Experiment creation
# ---------------------------------------------------------------------------

class TestExperimentCreate:

    @pytest.fixture
    def hypothesis_id(self, engine_env):
        from engine.hypothesis import generate
        ids = generate(CLIENT, BRIEF_ID)
        return ids[0]

    def test_create_returns_string_id(self, engine_env, hypothesis_id):
        """create() must return a string experiment ID."""
        from engine.experiment import create
        exp_id = create(CLIENT, hypothesis_id)
        assert isinstance(exp_id, str)

    def test_create_id_has_exp_prefix(self, engine_env, hypothesis_id):
        """The returned experiment ID must start with 'exp-'."""
        from engine.experiment import create
        exp_id = create(CLIENT, hypothesis_id)
        assert exp_id.startswith("exp-"), f"Got {exp_id!r}"

    def test_create_makes_markdown_file(self, engine_env, hypothesis_id):
        """create() must produce a .md file in the experiments/ folder."""
        from engine.experiment import create
        exp_id = create(CLIENT, hypothesis_id)
        exp_path = engine_env / "vault" / "clients" / CLIENT / "experiments" / f"{exp_id}.md"
        assert exp_path.exists()

    def test_create_file_has_required_frontmatter(self, engine_env, hypothesis_id):
        """The experiment file must have all required frontmatter fields."""
        from engine.experiment import create
        exp_id = create(CLIENT, hypothesis_id)
        exp_path = engine_env / "vault" / "clients" / CLIENT / "experiments" / f"{exp_id}.md"
        fm, _ = read_markdown(exp_path)
        for field in ("id", "hypothesis_id", "client_id", "title", "methodology", "status", "created"):
            assert field in fm, f"Missing frontmatter field: {field}"

    def test_create_links_correct_hypothesis(self, engine_env, hypothesis_id):
        """The experiment file must reference the correct hypothesis_id."""
        from engine.experiment import create
        exp_id = create(CLIENT, hypothesis_id)
        exp_path = engine_env / "vault" / "clients" / CLIENT / "experiments" / f"{exp_id}.md"
        fm, _ = read_markdown(exp_path)
        assert fm["hypothesis_id"] == hypothesis_id

    def test_create_status_is_pending(self, engine_env, hypothesis_id):
        """A newly created experiment must have status 'pending'."""
        from engine.experiment import create
        exp_id = create(CLIENT, hypothesis_id)
        exp_path = engine_env / "vault" / "clients" / CLIENT / "experiments" / f"{exp_id}.md"
        fm, _ = read_markdown(exp_path)
        assert fm["status"] == "pending"

    def test_create_missing_hypothesis_raises(self, engine_env):
        """create() must raise FileNotFoundError for a nonexistent hypothesis."""
        from engine.experiment import create
        with pytest.raises(FileNotFoundError):
            create(CLIENT, "hyp-999")


# ---------------------------------------------------------------------------
# TEST 3 — Result logging
# ---------------------------------------------------------------------------

class TestResultLogging:

    @pytest.fixture
    def experiment_id(self, engine_env):
        from engine.hypothesis import generate
        from engine.experiment import create
        hyp_ids = generate(CLIENT, BRIEF_ID)
        return create(CLIENT, hyp_ids[0])

    def test_log_result_returns_string_id(self, engine_env, experiment_id):
        """log_result() must return a string result ID."""
        from engine.results import log_result
        res_id = log_result(CLIENT, experiment_id, "A", "conversion_rate", 0.25)
        assert isinstance(res_id, str)

    def test_log_result_creates_markdown_file(self, engine_env, experiment_id):
        """log_result() must create a .md file in the results/ folder."""
        from engine.results import log_result
        res_id = log_result(CLIENT, experiment_id, "A", "conversion_rate", 0.25)
        res_path = engine_env / "vault" / "clients" / CLIENT / "results" / f"{res_id}.md"
        assert res_path.exists()

    def test_log_result_has_required_frontmatter(self, engine_env, experiment_id):
        """The result file must have all required frontmatter fields."""
        from engine.results import log_result
        res_id = log_result(CLIENT, experiment_id, "B", "conversion_rate", 0.35)
        res_path = engine_env / "vault" / "clients" / CLIENT / "results" / f"{res_id}.md"
        fm, _ = read_markdown(res_path)
        for field in ("id", "experiment_id", "client_id", "condition", "metric", "value", "winner", "status", "recorded_on"):
            assert field in fm, f"Missing frontmatter field: {field}"

    def test_log_result_stores_condition_and_metric(self, engine_env, experiment_id):
        """condition and metric must be stored in frontmatter."""
        from engine.results import log_result
        res_id = log_result(CLIENT, experiment_id, "control", "click_rate", 0.08)
        res_path = engine_env / "vault" / "clients" / CLIENT / "results" / f"{res_id}.md"
        fm, _ = read_markdown(res_path)
        assert fm["condition"] == "control"
        assert fm["metric"] == "click_rate"

    def test_log_result_winner_is_false_initially(self, engine_env, experiment_id):
        """A freshly logged result must have winner set to false."""
        from engine.results import log_result
        res_id = log_result(CLIENT, experiment_id, "A", "revenue", 1200.0)
        res_path = engine_env / "vault" / "clients" / CLIENT / "results" / f"{res_id}.md"
        fm, _ = read_markdown(res_path)
        assert fm["winner"] == "false"

    def test_log_result_notes_stored(self, engine_env, experiment_id):
        """Optional notes must appear in the result file body."""
        from engine.results import log_result
        res_id = log_result(CLIENT, experiment_id, "A", "bounce_rate", 0.4, notes="Early data only")
        res_path = engine_env / "vault" / "clients" / CLIENT / "results" / f"{res_id}.md"
        _, body = read_markdown(res_path)
        assert "Early data only" in body

    def test_list_results_returns_matching_results(self, engine_env, experiment_id):
        """list_results() must return all results for the given experiment."""
        from engine.results import log_result, list_results
        log_result(CLIENT, experiment_id, "A", "ctr", 0.12)
        log_result(CLIENT, experiment_id, "B", "ctr", 0.18)
        results = list_results(CLIENT, experiment_id)
        assert len(results) == 2

    def test_list_results_filters_by_experiment(self, engine_env):
        """list_results() must not include results from other experiments."""
        from engine.hypothesis import generate
        from engine.experiment import create
        from engine.results import log_result, list_results

        hyp_ids = generate(CLIENT, BRIEF_ID)
        exp1 = create(CLIENT, hyp_ids[0])
        exp2 = create(CLIENT, hyp_ids[1])

        log_result(CLIENT, exp1, "A", "metric", 0.1)
        log_result(CLIENT, exp2, "A", "metric", 0.2)

        r1 = list_results(CLIENT, exp1)
        r2 = list_results(CLIENT, exp2)

        assert len(r1) == 1 and r1[0]["experiment_id"] == exp1
        assert len(r2) == 1 and r2[0]["experiment_id"] == exp2

    def test_list_results_empty_when_none(self, engine_env):
        """list_results() must return an empty list when no results exist."""
        from engine.results import list_results
        results = list_results(CLIENT, "exp-nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# TEST 4 — Winner selection
# ---------------------------------------------------------------------------

class TestWinnerSelection:

    @pytest.fixture
    def experiment_with_results(self, engine_env):
        from engine.hypothesis import generate
        from engine.experiment import create
        from engine.results import log_result
        hyp_ids = generate(CLIENT, BRIEF_ID)
        exp_id = create(CLIENT, hyp_ids[0])
        log_result(CLIENT, exp_id, "A", "conversion_rate", 0.20)
        log_result(CLIENT, exp_id, "B", "conversion_rate", 0.35)
        return exp_id

    def test_select_winner_returns_dict(self, engine_env, experiment_with_results):
        """select_winner() must return a dict."""
        from engine.winner import select_winner
        result = select_winner(CLIENT, experiment_with_results)
        assert isinstance(result, dict)

    def test_select_winner_identifies_highest_value(self, engine_env, experiment_with_results):
        """select_winner() must pick the result with the highest value."""
        from engine.winner import select_winner
        summary = select_winner(CLIENT, experiment_with_results)
        assert summary["winner_value"] == pytest.approx(0.35)

    def test_select_winner_marks_winner_in_file(self, engine_env, experiment_with_results):
        """The winning result file must have winner=true after selection."""
        from engine.winner import select_winner
        from engine.results import list_results
        summary = select_winner(CLIENT, experiment_with_results)
        results = list_results(CLIENT, experiment_with_results)
        winner = next(r for r in results if r["id"] == summary["winner_id"])
        assert winner["winner"] == "true"

    def test_select_winner_marks_losers_false(self, engine_env, experiment_with_results):
        """Non-winning results must have winner=false after selection."""
        from engine.winner import select_winner
        from engine.results import list_results
        summary = select_winner(CLIENT, experiment_with_results)
        results = list_results(CLIENT, experiment_with_results)
        for r in results:
            if r["id"] != summary["winner_id"]:
                assert r["winner"] == "false", f"{r['id']} should not be winner"

    def test_select_winner_updates_experiment_status(self, engine_env, experiment_with_results):
        """The experiment file must have status='complete' after winner selection."""
        from engine.winner import select_winner
        select_winner(CLIENT, experiment_with_results)
        exp_path = (
            engine_env / "vault" / "clients" / CLIENT
            / "experiments" / f"{experiment_with_results}.md"
        )
        fm, _ = read_markdown(exp_path)
        assert fm["status"] == "complete"

    def test_select_winner_status_final(self, engine_env, experiment_with_results):
        """All results must have status='final' after winner selection."""
        from engine.winner import select_winner
        from engine.results import list_results
        select_winner(CLIENT, experiment_with_results)
        results = list_results(CLIENT, experiment_with_results)
        for r in results:
            assert r["status"] == "final"

    def test_select_winner_returns_correct_keys(self, engine_env, experiment_with_results):
        """select_winner() return dict must contain the expected keys."""
        from engine.winner import select_winner
        summary = select_winner(CLIENT, experiment_with_results)
        expected_keys = {"winner_id", "winner_condition", "winner_metric", "winner_value", "experiment_id", "total_results"}
        assert expected_keys.issubset(summary.keys())

    def test_select_winner_total_results_count(self, engine_env, experiment_with_results):
        """total_results must equal the number of results logged."""
        from engine.winner import select_winner
        summary = select_winner(CLIENT, experiment_with_results)
        assert summary["total_results"] == 2

    def test_select_winner_no_results_raises(self, engine_env):
        """select_winner() must raise ValueError when no results exist."""
        from engine.winner import select_winner
        with pytest.raises(ValueError, match="No results found"):
            select_winner(CLIENT, "exp-nonexistent")

    def test_select_winner_single_result(self, engine_env):
        """select_winner() must work correctly with a single result (always wins)."""
        from engine.hypothesis import generate
        from engine.experiment import create
        from engine.results import log_result
        from engine.winner import select_winner

        hyp_ids = generate(CLIENT, BRIEF_ID)
        exp_id = create(CLIENT, hyp_ids[2])
        log_result(CLIENT, exp_id, "only", "nps", 42.0)

        summary = select_winner(CLIENT, exp_id)
        assert summary["winner_condition"] == "only"
        assert summary["winner_value"] == pytest.approx(42.0)

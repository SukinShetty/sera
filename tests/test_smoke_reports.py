"""
tests/test_smoke_reports.py — Smoke tests for the reports/ module (Session 4).

Run with: python -m pytest tests/test_smoke_reports.py -v
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.file_io import write_markdown


# ---------------------------------------------------------------------------
# Fixtures — build a minimal client vault in a temp directory
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_vault(tmp_path, monkeypatch):
    """
    Patch PROJECT_ROOT and CONFIG so all SERA modules read/write to tmp_path.
    Creates a minimal client vault: one brief, two hypotheses, two experiments,
    four results (two per experiment).
    """
    # Patch config paths to point at tmp_path
    import shared.config as cfg_module
    monkeypatch.setattr(cfg_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setitem(
        cfg_module.CONFIG["paths"], "clients_root", "vault/clients/"
    )
    monkeypatch.setitem(
        cfg_module.CONFIG["paths"], "reports_root", "reports/output/"
    )

    client = "test-client"
    brief_id = "brief-001"
    client_dir = tmp_path / "vault" / "clients" / client

    # Brief
    write_markdown(
        client_dir / "briefs" / f"{brief_id}.md",
        "# Brief\n\nResearch into user engagement improvements.",
        {
            "title": "Engagement Research Q1",
            "client_id": client,
            "status": "active",
            "created": "2026-05-01",
        },
    )

    # Hypothesis 1
    write_markdown(
        client_dir / "hypotheses" / "hyp-001.md",
        (
            "# Hypothesis: Shorter Onboarding\n\n"
            "> **If we shorten onboarding, then activation will increase.**\n\n"
            "## Rationale\n\nFewer steps = less drop-off."
        ),
        {
            "id": "hyp-001",
            "brief_id": brief_id,
            "client_id": client,
            "title": "Shorter Onboarding Wins",
            "status": "active",
            "created": "2026-05-02",
        },
    )

    # Hypothesis 2
    write_markdown(
        client_dir / "hypotheses" / "hyp-002.md",
        (
            "# Hypothesis: Email Timing\n\n"
            "> **If we send emails at 9am, then open rates will rise.**\n\n"
            "## Rationale\n\nMorning sends outperform afternoon sends."
        ),
        {
            "id": "hyp-002",
            "brief_id": brief_id,
            "client_id": client,
            "title": "Morning Email Timing",
            "status": "draft",
            "created": "2026-05-03",
        },
    )

    # Experiment 1 for hyp-001
    write_markdown(
        client_dir / "experiments" / "exp-001.md",
        "# Experiment: Test Onboarding",
        {
            "id": "exp-001",
            "hypothesis_id": "hyp-001",
            "client_id": client,
            "title": "Test: Shorter Onboarding Wins",
            "methodology": "A/B test",
            "status": "complete",
            "created": "2026-05-04",
        },
    )

    # Experiment 2 for hyp-002
    write_markdown(
        client_dir / "experiments" / "exp-002.md",
        "# Experiment: Test Email Timing",
        {
            "id": "exp-002",
            "hypothesis_id": "hyp-002",
            "client_id": client,
            "title": "Test: Morning Email Timing",
            "methodology": "A/B test",
            "status": "pending",
            "created": "2026-05-05",
        },
    )

    # Results for exp-001
    write_markdown(
        client_dir / "results" / "res-exp-001-a.md",
        "# Result A",
        {
            "id": "res-exp-001-a",
            "experiment_id": "exp-001",
            "client_id": client,
            "condition": "A",
            "metric": "activation_rate",
            "value": "0.32",
            "winner": "false",
            "confidence": "0.0",
            "status": "final",
            "recorded_on": "2026-05-06",
        },
    )
    write_markdown(
        client_dir / "results" / "res-exp-001-b.md",
        "# Result B",
        {
            "id": "res-exp-001-b",
            "experiment_id": "exp-001",
            "client_id": client,
            "condition": "B",
            "metric": "activation_rate",
            "value": "0.54",
            "winner": "true",
            "confidence": "1.0",
            "status": "final",
            "recorded_on": "2026-05-06",
        },
    )

    return {"client": client, "brief_id": brief_id, "tmp_path": tmp_path}


# ===========================================================================
# TEST 1 — compiler
# ===========================================================================

class TestCompiler:

    def test_compile_report_data_returns_expected_keys(self, client_vault):
        from reports.compiler import compile_report_data

        data = compile_report_data(client_vault["client"], client_vault["brief_id"])

        assert "client" in data
        assert "brief_id" in data
        assert "brief" in data
        assert "hypotheses" in data
        assert "experiments" in data
        assert "all_results" in data
        assert "winners" in data

    def test_compile_reads_brief_correctly(self, client_vault):
        from reports.compiler import compile_report_data

        data = compile_report_data(client_vault["client"], client_vault["brief_id"])

        assert data["brief"]["frontmatter"]["title"] == "Engagement Research Q1"

    def test_compile_filters_hypotheses_by_brief_id(self, client_vault):
        from reports.compiler import compile_report_data

        data = compile_report_data(client_vault["client"], client_vault["brief_id"])

        # Both hyp-001 and hyp-002 belong to brief-001
        assert len(data["hypotheses"]) == 2
        hyp_ids = {h["id"] for h in data["hypotheses"]}
        assert hyp_ids == {"hyp-001", "hyp-002"}

    def test_compile_reads_experiments_per_hypothesis(self, client_vault):
        from reports.compiler import compile_report_data

        data = compile_report_data(client_vault["client"], client_vault["brief_id"])

        assert len(data["experiments"]) == 2

    def test_compile_reads_results_and_flattens(self, client_vault):
        from reports.compiler import compile_report_data

        data = compile_report_data(client_vault["client"], client_vault["brief_id"])

        # exp-001 has 2 results; exp-002 has none
        assert len(data["all_results"]) == 2

    def test_compile_identifies_winner(self, client_vault):
        from reports.compiler import compile_report_data

        data = compile_report_data(client_vault["client"], client_vault["brief_id"])

        assert len(data["winners"]) >= 1
        top = data["winners"][0]
        assert "confidence" in top
        assert "title" in top
        assert "outcome" in top

    def test_compile_raises_if_brief_missing(self, client_vault, monkeypatch):
        from reports.compiler import compile_report_data

        with pytest.raises(FileNotFoundError):
            compile_report_data(client_vault["client"], "brief-999")

    def test_compile_extracts_hypothesis_text(self, client_vault):
        from reports.compiler import compile_report_data

        data = compile_report_data(client_vault["client"], client_vault["brief_id"])

        hyp = next(h for h in data["hypotheses"] if h["id"] == "hyp-001")
        assert "activation" in hyp["hypothesis"].lower() or "onboarding" in hyp["hypothesis"].lower()


# ===========================================================================
# TEST 2 — formatter
# ===========================================================================

class TestFormatter:

    def _minimal_data(self):
        return {
            "client": "test-co",
            "brief_id": "brief-001",
            "brief": {
                "frontmatter": {
                    "title": "Test Brief",
                    "status": "active",
                    "created": "2026-05-01",
                },
                "body": "Research into user behaviour.",
            },
            "hypotheses": [
                {
                    "id": "hyp-001",
                    "title": "Engagement Hypothesis",
                    "hypothesis": "If we simplify the UX, engagement will rise.",
                    "status": "active",
                    "outcome": "Currently being tested",
                    "experiments": [],
                }
            ],
            "experiments": [],
            "all_results": [],
            "winners": [],
        }

    def test_render_returns_frontmatter_and_body(self):
        from reports.formatter import render_report

        fm, body = render_report(self._minimal_data())

        assert isinstance(fm, dict)
        assert isinstance(body, str)

    def test_frontmatter_has_required_fields(self):
        from reports.formatter import render_report

        fm, _ = render_report(self._minimal_data())

        assert "client_id" in fm
        assert "title" in fm
        assert "generated_on" in fm
        assert "format" in fm

    def test_body_contains_all_required_sections(self):
        from reports.formatter import render_report

        _, body = render_report(self._minimal_data())

        required_headings = [
            "## Executive Summary",
            "## Client & Research Context",
            "## Hypotheses Tested",
            "## Experiments Run",
            "## Result Comparison",
            "## Winner Summary",
            "## Recommendations",
            "## Next Experiments",
        ]
        for heading in required_headings:
            assert heading in body, f"Missing section: {heading}"

    def test_body_includes_client_id(self):
        from reports.formatter import render_report

        _, body = render_report(self._minimal_data())

        assert "test-co" in body

    def test_body_includes_hypothesis_title(self):
        from reports.formatter import render_report

        _, body = render_report(self._minimal_data())

        assert "Engagement Hypothesis" in body

    def test_fallback_summary_generated_without_ai(self):
        from reports.formatter import render_report

        # Ensure no API key is set so fallback kicks in
        with mock.patch.dict("os.environ", {}, clear=True):
            fm, body = render_report(self._minimal_data())

        assert "## Executive Summary" in body
        assert "Test Brief" in body

    def test_render_with_winner_shows_confidence(self):
        from reports.formatter import render_report

        data = self._minimal_data()
        data["winners"] = [
            {
                "title": "Exp 1 — B wins",
                "confidence": 0.85,
                "outcome": "Condition B achieved the highest activation_rate.",
                "experiment_id": "exp-001",
            }
        ]
        _, body = render_report(data)

        assert "85.0%" in body


# ===========================================================================
# TEST 3 — exporter
# ===========================================================================

class TestExporter:

    def test_export_creates_file(self, client_vault):
        from reports.exporter import export

        path = export(
            client_vault["client"],
            "report-brief-001-001",
            {"client_id": client_vault["client"], "title": "Test", "format": "markdown"},
            "# Test Report\n\nContent here.",
        )

        assert path.exists()
        assert path.suffix == ".md"

    def test_export_creates_parent_directories(self, tmp_path, monkeypatch):
        import shared.config as cfg_module
        monkeypatch.setattr(cfg_module, "PROJECT_ROOT", tmp_path)
        monkeypatch.setitem(cfg_module.CONFIG["paths"], "reports_root", "reports/output/")

        from reports.exporter import export

        path = export(
            "brand-new-client",
            "report-brief-001-001",
            {"client_id": "brand-new-client", "title": "T", "format": "markdown"},
            "Body.",
        )

        assert path.exists()
        assert "brand-new-client" in str(path)

    def test_export_writes_correct_content(self, client_vault):
        from reports.exporter import export
        from shared.file_io import read_markdown

        path = export(
            client_vault["client"],
            "report-brief-001-check",
            {"client_id": client_vault["client"], "title": "My Report", "format": "markdown"},
            "# My Report\n\nContent.",
        )

        fm, body = read_markdown(path)
        assert fm["title"] == "My Report"
        assert "Content" in body


# ===========================================================================
# TEST 4 — generator (end-to-end)
# ===========================================================================

class TestGenerator:

    def test_generate_returns_path(self, client_vault):
        from reports.generator import generate

        path = generate(client_vault["client"], client_vault["brief_id"])

        assert isinstance(path, Path)
        assert path.exists()

    def test_generate_creates_markdown_file(self, client_vault):
        from reports.generator import generate

        path = generate(client_vault["client"], client_vault["brief_id"])

        assert path.suffix == ".md"

    def test_generate_report_contains_all_sections(self, client_vault):
        from reports.generator import generate
        from shared.file_io import read_markdown

        path = generate(client_vault["client"], client_vault["brief_id"])
        fm, body = read_markdown(path)

        required_headings = [
            "## Executive Summary",
            "## Client & Research Context",
            "## Hypotheses Tested",
            "## Experiments Run",
            "## Result Comparison",
            "## Winner Summary",
            "## Recommendations",
            "## Next Experiments",
        ]
        for heading in required_headings:
            assert heading in body, f"Missing section in generated report: {heading}"

    def test_generate_frontmatter_has_client(self, client_vault):
        from reports.generator import generate
        from shared.file_io import read_markdown

        path = generate(client_vault["client"], client_vault["brief_id"])
        fm, _ = read_markdown(path)

        assert fm["client_id"] == client_vault["client"]

    def test_generate_increments_report_id(self, client_vault):
        from reports.generator import generate

        path1 = generate(client_vault["client"], client_vault["brief_id"])
        path2 = generate(client_vault["client"], client_vault["brief_id"])

        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_generate_raises_if_brief_missing(self, client_vault):
        from reports.generator import generate

        with pytest.raises(FileNotFoundError):
            generate(client_vault["client"], "brief-does-not-exist")

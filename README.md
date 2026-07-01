# SERA Vault OS

**Self-Evolving Research Architecture** — a local-first, Obsidian-integrated operating system for running structured research.

![version](https://img.shields.io/badge/version-0.2.0-blue)
![python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![license](https://img.shields.io/badge/license-MIT-green)
![interface](https://img.shields.io/badge/interface-CLI%20%2B%20Streamlit-orange)

SERA turns a research brief into a structured vault of hypotheses, experiments, logged results, a selected winner, and a client-ready report — from the command line or a local web UI. Every artifact is a plain Markdown file in an Obsidian-compatible vault. You own all the data; nothing leaves your machine unless you choose to share it.

```
Brief → Hypotheses → Experiments → Results → Winner → Report
```

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Web UI](#web-ui-streamlit)
- [CLI Reference](#cli-reference)
- [Vault Structure](#vault-structure)
- [Use Cases](#use-cases)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [Project Layout](#project-layout)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Most research tooling is either too heavy (enterprise platforms with vendor lock-in) or too light (a notes app with no workflow). SERA fills the gap for founders, consultants, and product teams who run research regularly and need a structured, repeatable process — without a SaaS subscription or a data scientist on retainer.

The research workflow is the same every time:

1. Write a brief.
2. Generate testable hypotheses.
3. Design and run experiments.
4. Log what you measured.
5. Pick the winner.
6. Ship a client-ready report.

SERA automates the scaffolding and report generation so you focus on the research, not the paperwork. Optional Claude integration writes hypotheses and report prose; without an API key, SERA falls back to built-in templated generators so the system always works — even offline.

---

## Features

- **Full research lifecycle** — brief to report in one toolchain.
- **Local-first & private** — every artifact is Markdown on your disk. No cloud, no lock-in.
- **Obsidian-native** — vaults open directly in Obsidian with wiki-links between artifacts.
- **Two interfaces** — a Click-based CLI and a Streamlit web UI that share the same vault.
- **Per-client isolation** — each client gets an independent vault tree.
- **Optional AI generation** — set `ANTHROPIC_API_KEY` for Claude-authored hypotheses and reports; graceful fallback without it.
- **Tested** — an automated test suite covers the shared foundation, CLI, engine, and reports.

---

## Installation

**Requirements:** Python 3.10+ and `pip`.

```bash
# Clone the repository
git clone https://github.com/SukinShetty/sera.git
cd sera

# (Recommended) create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify the CLI
python -m cli.main --version
```

### Optional: AI-powered generation

Hypothesis and report prose can be authored by Claude. This requires the `anthropic` package and an API key:

```bash
pip install anthropic

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

Without a key, SERA uses built-in templated generators — every command still produces complete output.

### Run the tests

```bash
python -m pytest tests/ -v
```

---

## Quick Start

A complete research cycle for a new client:

```bash
# 1. Create an isolated client vault
python -m cli.main vault init --client acme-corp

# 2. Write a brief (or create it in the Web UI)
#    → vault/clients/acme-corp/briefs/brief-001.md

# 3. Generate three hypotheses from the brief
python -m cli.main hypothesis generate --client acme-corp --brief brief-001

# 4. Create an experiment from a hypothesis
python -m cli.main experiment create --client acme-corp --hypothesis hyp-001

# 5. Log measured results (Python API or Web UI)
python - <<'PY'
from engine.results import log_result
log_result("acme-corp", "exp-001", "A", "conversion_rate", 0.09, notes="Control")
log_result("acme-corp", "exp-001", "B", "conversion_rate", 0.17, notes="Treatment")
PY

# 6. Select the winning condition (Python API or Web UI)
python -c "from engine.winner import select_winner; print(select_winner('acme-corp','exp-001'))"

# 7. Generate the client-ready report
python -m cli.main report generate --client acme-corp --brief brief-001
#    → reports/output/acme-corp/report-brief-001-001.md
```

A brief is the only file you write by hand. Everything downstream is generated. Example brief:

```markdown
---
title: Onboarding Conversion Study
client_id: acme-corp
status: active
created: 2026-05-12
---

# Research Brief: Onboarding Conversion Study

## Objective
Increase trial-to-paid conversion from 8% to 15% within 60 days.

## Research Questions
1. What are the top three friction points in the onboarding flow?
2. Which onboarding steps correlate most strongly with paid conversion?
```

---

## Web UI (Streamlit)

SERA ships a local web UI that mirrors the full CLI workflow:

```bash
streamlit run frontend/app.py
```

Opens at `http://localhost:8501`. Use the sidebar to create or switch client vaults; each tab maps to one step of the workflow:

| Tab | Purpose |
|-----|---------|
| **Brief** | Create or view research briefs |
| **Hypotheses** | Generate three hypotheses from a brief |
| **Experiments** | Create an experiment from a hypothesis |
| **Results** | Log measured values per condition (A, B, control, …) |
| **Winner** | Select the winning condition |
| **Report** | Generate and preview the full Markdown report |

The CLI and Web UI share the same vault — work done in one is immediately visible in the other.

---

## CLI Reference

All commands follow `python -m cli.main <group> <command> [OPTIONS]`.

### `vault` — manage client vaults

| Command | Description |
|---------|-------------|
| `vault init --client <name>` | Create a client vault with the standard folder tree |
| `vault list` | List all client vaults with item counts |
| `vault status --client <name>` | Show folder-by-folder status for a client |

### `hypothesis` — generate and list hypotheses

| Command | Description |
|---------|-------------|
| `hypothesis generate --client <name> --brief <id>` | Generate three hypotheses from a brief |
| `hypothesis list --client <name>` | List hypothesis files for a client |

### `experiment` — create and list experiments

| Command | Description |
|---------|-------------|
| `experiment create --client <name> --hypothesis <id>` | Scaffold an experiment from a hypothesis |
| `experiment list --client <name>` | List experiment files for a client |

### `report` — generate and list reports

| Command | Description |
|---------|-------------|
| `report generate --client <name> --brief <id>` | Compile a full research report for a brief |
| `report list --client <name>` | List reports for a client |

> **Note:** Result logging and winner selection are currently exposed via the Web UI and the Python API (`engine.results.log_result`, `engine.winner.select_winner`); dedicated CLI commands are on the roadmap.

---

## Vault Structure

Every client gets an isolated, Obsidian-compatible tree:

```
vault/
  clients/
    {client_id}/
      _meta.md             # Obsidian entry point for this client
      briefs/              # Research briefs (you write these)
      hypotheses/          # Generated by engine.hypothesis
      experiments/         # Created by engine.experiment
      results/             # Logged by engine.results

reports/
  output/
    {client_id}/
      report-brief-001-001.md   # Final client-ready report
```

All files are standard Markdown with YAML frontmatter — open them in Obsidian or any editor.

---

## Use Cases

- **Conversion rate optimisation** — structured A/B tests on onboarding, pricing, or checkout, with a report showing which variant wins and by how much.
- **Product-market fit research** — test positioning hypotheses per segment, log scores, and report the strongest signal.
- **Consulting engagements** — one isolated vault per client, with a polished report at the end of each sprint.
- **Startup validation sprints** — run 5–10 experiments a week across pricing, messaging, and targeting; SERA tracks what's been tested and what's next.
- **Internal strategy** — force disciplined decisions before committing engineering resources.

---

## Limitations

| Area | Current limitation (v0.2.0) |
|------|------------------------------|
| Result logging | No CLI command yet — use the Web UI or Python API |
| Winner selection | No CLI command yet — use the Web UI or Python API |
| Brief creation | No `brief create` CLI command — use the Web UI or write the Markdown manually |
| AI generation | Requires the `anthropic` package and `ANTHROPIC_API_KEY`; falls back to templates otherwise |
| Report format | Markdown only — no PDF or HTML export yet |
| Collaboration | Local-only; no cloud sync or multi-user support |
| Metrics | Numeric values only — no categorical or qualitative data |

---

## Roadmap

- **v0.2.0 — Streamlit frontend** ✅ *(shipped)* — local web UI covering the full workflow; CLI unchanged.
- **v0.3.0 — Report formats** — PDF/HTML export, Slack/email delivery hooks.
- **v0.4.0 — Obsidian integration** — custom plugin, Dataview dashboards, graph-view links.
- **v0.5.0 — Collaboration** — optional cloud sync, shared vaults with access control.
- **v1.0.0 — Self-evolving layer** — SERA reads its own past results and proposes the next hypotheses automatically, closing the research loop.

---

## Project Layout

```
sera-vault-os/
  shared/         # Config, file I/O, validators
  cli/            # Click CLI commands
  vault/          # Obsidian scaffold + templates
  engine/         # Hypothesis, experiment, results, winner
  reports/        # Compiler, formatter, exporter
  frontend/       # Streamlit web UI
  tests/          # Automated test suite
  requirements.txt
  sera_config.json
```

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository and create a feature branch.
2. Add or update tests for your change.
3. Ensure `python -m pytest tests/ -v` passes.
4. Open a pull request describing the change and its motivation.

---

## License

Released under the [MIT License](LICENSE).

---

<sub>SERA Vault OS was built with Claude Code using a parallel multi-agent workflow: independent sessions on isolated git worktrees each owned one module (`shared`, `cli`, `vault`, `engine`, `reports`, `frontend`), coordinated through shared memory and integrated in a single verified pass. See `DEMO.md` for a full walkthrough.</sub>

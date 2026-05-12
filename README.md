# SERA Vault OS

**Self-Evolving Research Architecture — v0.1.0**

A local-first, Research-as-a-Service operating system integrated with Obsidian.
SERA turns a research brief into a structured vault of hypotheses, experiments,
logged results, a selected winner, and a client-ready report — all from the CLI.

---

## What It Is

SERA Vault OS is a command-line research engine that runs the full scientific
research cycle on your local machine:

```
Brief → Hypotheses → Experiments → Results → Winner → Report
```

Every artifact is a Markdown file stored in an Obsidian-compatible vault.
You own all the data. Nothing leaves your machine unless you choose to share it.

---

## Why It Exists

Most research tools are either:
- Too heavy (enterprise platforms with vendor lock-in), or
- Too light (just a notes app with no workflow)

SERA fills the gap for founders, consultants, and product teams who run
research regularly and need a structured, repeatable process — without a SaaS
subscription or a data scientist on retainer.

The research workflow is the same every time:
1. Write a brief
2. Generate testable hypotheses
3. Design and run experiments
4. Log what you measured
5. Pick the winner
6. Ship a client-ready report

SERA automates the scaffolding and report generation so you focus on the
research itself, not the paperwork.

---

## How It Was Built

SERA was built using a parallel multi-agent architecture inside **Claude Code**:

### Tool Stack
| Tool | Role |
|------|------|
| **Claude Code** | AI coding agent running each session |
| **Git Worktrees** | Isolated branches so 4 sessions built in parallel without conflicts |
| **Nemp Memory** | Shared memory (`.nemp/memories.json`) read and written by every session |
| **`nemp_memory.json`** | Human-readable cross-session architecture document |

### Session Architecture

Each session owned exactly one folder. No session touched another's code.

```
Session 0 (main branch)  →  shared/          Foundation: config, file I/O, validators
Session 1 (session/cli)  →  cli/             Click CLI: vault, hypothesis, experiment, report
Session 2 (session/vault)→  vault/           Obsidian scaffold, templates, JSON schemas
Session 3 (session/engine)→ engine/          Hypothesis gen, experiment runner, winner logic
Session 4 (session/reports)→reports/         Report compiler, Jinja2 formatter, exporter
```

Sessions ran in parallel git worktrees at:
```
C:\Users\User\sera-vault-os       ← master (Session 0)
C:\Users\User\sera-session-1      ← session/cli
C:\Users\User\sera-session-2      ← session/vault
C:\Users\User\sera-session-3      ← session/engine
C:\Users\User\sera-session-4      ← session/reports
```

All four session branches were merged into master during a single integration
pass that fixed one cross-session bug (a subfolder naming mismatch between the
CLI and the engine) and verified 79/79 tests + a full end-to-end smoke test.

---

## Installation

### Requirements
- Python 3.10 or later
- pip

### Steps

```bash
# 1. Clone or navigate to the project
cd C:\Users\User\sera-vault-os

# 2. (Optional but recommended) Create a virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify the CLI works
python -m cli.main --version
# → sera, version 0.1.0

# 5. (Optional) Enable AI-powered hypothesis and report generation
# Set your Anthropic API key — SERA falls back to templated output without it.
set ANTHROPIC_API_KEY=sk-ant-...    # Windows
# export ANTHROPIC_API_KEY=sk-ant-... # macOS / Linux
```

### Run Tests
```bash
python -m pytest tests/ -v
# 79 passed
```

---

## CLI Reference

All commands follow the pattern:
```
python -m cli.main <group> <command> [OPTIONS]
```

### `vault` — Manage client vaults

| Command | Description |
|---------|-------------|
| `vault init --client <name>` | Create a new client vault with the standard folder structure |
| `vault list` | List all existing client vaults with item counts |
| `vault status --client <name>` | Show folder-by-folder status for a client |

```bash
python -m cli.main vault init --client acme-corp
python -m cli.main vault list
python -m cli.main vault status --client acme-corp
```

### `hypothesis` — Generate and list hypotheses

| Command | Description |
|---------|-------------|
| `hypothesis generate --client <name> --brief <brief_id>` | Generate 3 hypotheses from a brief (uses Claude API or fallback) |
| `hypothesis list --client <name>` | List all hypothesis files for a client |

```bash
python -m cli.main hypothesis generate --client acme-corp --brief brief-001
python -m cli.main hypothesis list --client acme-corp
```

### `experiment` — Create and list experiments

| Command | Description |
|---------|-------------|
| `experiment create --client <name> --hypothesis <hyp_id>` | Create an experiment from a hypothesis |
| `experiment list --client <name>` | List all experiment files for a client |

```bash
python -m cli.main experiment create --client acme-corp --hypothesis hyp-001
python -m cli.main experiment list --client acme-corp
```

### `report` — Generate and list reports

| Command | Description |
|---------|-------------|
| `report generate --client <name> --brief <brief_id>` | Generate a full research report for a brief |
| `report list --client <name>` | List all reports for a client |

```bash
python -m cli.main report generate --client acme-corp --brief brief-001
python -m cli.main report list --client acme-corp
```

---

## End-to-End Workflow

Here is a complete research cycle for a new client:

### Step 1 — Create the client vault
```bash
python -m cli.main vault init --client acme-corp
```
Creates:
```
vault/clients/acme-corp/
    _meta.md
    briefs/
    hypotheses/
    experiments/
    results/
```

### Step 2 — Write a research brief

Create `vault/clients/acme-corp/briefs/brief-001.md`:

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

### Step 3 — Generate hypotheses
```bash
python -m cli.main hypothesis generate --client acme-corp --brief brief-001
```
Writes `hyp-001.md`, `hyp-002.md`, `hyp-003.md` to `vault/clients/acme-corp/hypotheses/`.

### Step 4 — Create an experiment
```bash
python -m cli.main experiment create --client acme-corp --hypothesis hyp-001
```
Writes `exp-001.md` to `vault/clients/acme-corp/experiments/`.

### Step 5 — Log results (via Python API)

After running your actual experiment, log the measured outcomes:

```python
from engine.results import log_result

log_result("acme-corp", "exp-001", "A", "conversion_rate", 0.09, notes="Control: existing flow")
log_result("acme-corp", "exp-001", "B", "conversion_rate", 0.17, notes="Treatment: simplified onboarding")
```

### Step 6 — Select the winner
```python
from engine.winner import select_winner

summary = select_winner("acme-corp", "exp-001")
print(summary)
# {'winner_id': 'res-exp-001-b', 'winner_condition': 'B',
#  'winner_metric': 'conversion_rate', 'winner_value': 0.17,
#  'experiment_id': 'exp-001', 'total_results': 2}
```

### Step 7 — Generate the report
```bash
python -m cli.main report generate --client acme-corp --brief brief-001
```
Writes a complete Markdown report to `reports/output/acme-corp/report-brief-001-001.md`.

---

## Vault Structure

Every client gets an isolated folder tree:

```
vault/
  clients/
    {client_id}/
      _meta.md             ← Obsidian entry point for this client
      briefs/              ← Research briefs (you write these)
        brief-001.md
      hypotheses/          ← Generated by engine.hypothesis
        hyp-001.md
        hyp-002.md
        hyp-003.md
      experiments/         ← Created by engine.experiment
        exp-001.md
      results/             ← Logged by engine.results
        res-exp-001-a.md
        res-exp-001-b.md

reports/
  output/
    {client_id}/
      report-brief-001-001.md   ← Final client-ready report
```

All files are standard Markdown with YAML frontmatter — open them directly in
Obsidian or any Markdown editor.

---

## Research-as-a-Service Use Cases

### Conversion Rate Optimisation
Run structured A/B tests on onboarding flows, pricing pages, or checkout steps.
Log conversion rates per condition. Get a report showing which variant wins and
by how much.

### Product-Market Fit Research
Test positioning hypotheses with early adopters. Log qualitative scores or NPS
per segment. Select the segment with the strongest signal. Report the findings
to stakeholders.

### Consulting Engagements
Create a separate vault per client. Each client's briefs, experiments, and
reports are fully isolated. Generate a polished Markdown report at the end of
each sprint. Export or print for delivery.

### Startup Validation Sprints
Run 5-10 experiments in a week across pricing, messaging, and audience targeting.
Log results daily. SERA automatically tracks which hypotheses have been tested,
which haven't, and what the next experiments should be.

### Internal Strategy Research
Use SERA internally to test product bets before committing engineering resources.
Brief → hypothesis → experiment → winner is a forcing function for disciplined
decision-making.

---

## Current Limitations (v0.1.0)

| Area | Limitation |
|------|-----------|
| **Result logging** | No CLI command for `log_result` — use the Python API directly |
| **Winner selection** | No CLI command for `select_winner` — use the Python API directly |
| **Briefs** | No `brief create` CLI command — write the Markdown file manually |
| **AI generation** | Requires `ANTHROPIC_API_KEY`; falls back to templated output without it |
| **Report format** | Markdown only — no PDF or HTML export yet |
| **Multi-user** | Local-only; no collaboration or cloud sync |
| **Obsidian plugins** | Vault is Obsidian-compatible but no custom plugin or Dataview queries included |
| **Metrics** | Numeric values only — no support for categorical or qualitative data |

---

## Roadmap

### v0.2.0 — Full CLI coverage
- `sera brief create --client <name> --title "..."` — create briefs from the CLI
- `sera results log --client <name> --experiment <id> --condition A --metric ctr --value 0.12`
- `sera results winner --client <name> --experiment <id>`

### v0.3.0 — Report formats
- PDF export via `weasyprint` or `pandoc`
- HTML export with embedded charts
- Slack / email delivery hook

### v0.4.0 — Obsidian integration
- Custom Obsidian plugin for real-time vault browsing
- Dataview query templates for experiment dashboards
- Graph view link generation

### v0.5.0 — Multi-client collaboration
- Optional cloud sync (S3 / Dropbox)
- Shared vaults with access control
- Team annotations on results

### v1.0.0 — Self-evolving layer
- SERA reads its own past experiment results and proposes the next hypotheses
  automatically, closing the research loop without human prompting

---

## Project Layout

```
sera-vault-os/
  shared/         Config, file I/O, validators  (Session 0)
  cli/            Click CLI commands             (Session 1)
  vault/          Obsidian scaffold + templates  (Session 2)
  engine/         Hypothesis, experiment, winner (Session 3)
  reports/        Compiler, formatter, exporter  (Session 4)
  tests/          79 automated tests
  sera_config.json
  nemp_memory.json
  requirements.txt
```

---

## License

MIT — use it, fork it, build on it.

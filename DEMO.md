# SERA Vault OS — Demo Guide

**A walkthrough for video, live demo, or client presentation.**

---

## What You're About to See

SERA Vault OS runs the full research cycle in minutes:

> Brief → Hypotheses → Experiment → Results → Winner → Report

Every artifact is a real Markdown file, readable in Obsidian or any editor.
No cloud. No SaaS. No lock-in. All local.

---

## Demo Script (Video Narration)

### Opening (30 seconds)

> "Most research stays stuck in slide decks and Notion pages that nobody revisits.
> SERA Vault OS turns research into a structured, repeatable operating system —
> local-first, Obsidian-integrated, and CLI-driven.
>
> What you're about to see is the full research cycle: from a blank brief
> to a client-ready report, in under five minutes."

---

### Scene 1 — Show the project structure (30 seconds)

Open your terminal in `C:\Users\User\sera-vault-os`.

```bash
python -m cli.main --version
```

**Say:**
> "SERA has four modules: vault, CLI, engine, and reports.
> Each was built in parallel by a separate Claude Code agent session
> on its own git worktree. They never touched each other's code."

Show the folder tree briefly:
```
shared/    ← foundation
cli/       ← Session 1
vault/     ← Session 2
engine/    ← Session 3
reports/   ← Session 4
```

---

### Scene 2 — Create a client vault (45 seconds)

```bash
python -m cli.main vault init --client acme-corp
```

**Say:**
> "Every client gets their own isolated vault.
> SERA creates four folders automatically: briefs, hypotheses, experiments, results.
> This is the Obsidian-compatible structure. Open this folder in Obsidian and
> you get a full knowledge graph of the client's research history."

```bash
python -m cli.main vault list
python -m cli.main vault status --client acme-corp
```

---

### Scene 3 — Write the research brief (45 seconds)

Open `vault/clients/acme-corp/briefs/brief-001.md` in your editor or show the
pre-written file.

**Say:**
> "The brief is the only thing you write yourself.
> It has a title, objective, and research questions.
> Everything else — hypotheses, experiments, results, report —
> SERA generates from this one file."

Show the frontmatter:
```yaml
---
title: Onboarding Conversion Study
client_id: acme-corp
status: active
created: 2026-05-12
---
```

And the body:
```markdown
## Objective
Increase trial-to-paid conversion from 8% to 15%.

## Research Questions
1. What friction points block conversion?
2. Which onboarding steps correlate with paying?
```

---

### Scene 4 — Generate hypotheses (60 seconds)

```bash
python -m cli.main hypothesis generate --client acme-corp --brief brief-001
```

**Say:**
> "SERA reads the brief and generates three testable hypotheses.
> If you set an Anthropic API key, Claude writes them.
> If you don't, SERA uses a built-in fallback generator —
> so the system always works, even offline."

Open one of the generated files in your editor or Obsidian:

```markdown
# Hypothesis: Audience Alignment: Onboarding Conversion Study

> **If we align our offering more precisely with the target audience's core needs,
> then engagement will increase, because reducing friction converts more prospects.**

## Success Metrics
- Engagement rate increase >= 15%
- Bounce rate decrease >= 10%
- Conversion rate uplift >= 5%
```

**Say:**
> "Each hypothesis is a structured 'If X, then Y, because Z' statement.
> It has measurable success metrics built in.
> It links back to the brief with an Obsidian wiki link."

```bash
python -m cli.main hypothesis list --client acme-corp
```

---

### Scene 5 — Create an experiment (45 seconds)

```bash
python -m cli.main experiment create --client acme-corp --hypothesis hyp-001
```

**Say:**
> "Now we link a hypothesis to an experiment.
> SERA scaffolds the experiment file automatically —
> methodology, variables, expected outcome, status."

Show `exp-001.md`:

```markdown
# Experiment: Test: Audience Alignment

## Methodology
A/B test

## Variables
| Role          | Variable                      |
|---------------|-------------------------------|
| Independent   | Treatment condition (A vs B)  |
| Dependent     | Audience Alignment: ...       |
| Control       | All other factors held constant |

Status: pending
```

---

### Scene 6 — Log results (45 seconds)

**Say:**
> "After running the actual experiment,
> you log the measured values into SERA.
> Right now that's done via the Python API —
> a CLI command is on the v0.2.0 roadmap."

Show a quick Python snippet or a pre-run script:

```python
from engine.results import log_result

log_result("acme-corp", "exp-001", "A", "conversion_rate", 0.09,
           notes="Control: existing onboarding")
log_result("acme-corp", "exp-001", "B", "conversion_rate", 0.17,
           notes="Treatment: simplified 3-step onboarding")
```

Show the two result files created in `vault/clients/acme-corp/results/`.

---

### Scene 7 — Select the winner (30 seconds)

```python
from engine.winner import select_winner

summary = select_winner("acme-corp", "exp-001")
print(summary)
```

Output:
```python
{
  'winner_id': 'res-exp-001-b',
  'winner_condition': 'B',
  'winner_metric': 'conversion_rate',
  'winner_value': 0.17,
  'experiment_id': 'exp-001',
  'total_results': 2
}
```

**Say:**
> "SERA compares all conditions, picks the highest value,
> updates the winner flag in each result file, marks the experiment complete,
> and calculates confidence scores — all automatically."

---

### Scene 8 — Generate the report (60 seconds)

```bash
python -m cli.main report generate --client acme-corp --brief brief-001
```

**Say:**
> "This is where everything comes together.
> SERA walks the entire vault — brief, hypotheses, experiments, results —
> compiles them into a structured report, and writes it to disk."

Open `reports/output/acme-corp/report-brief-001-001.md`.

Show the sections:
```
## Executive Summary
## Client & Research Context
## Hypotheses Tested
## Experiments Run
## Result Comparison
## Winner Summary
## Recommendations
## Next Experiments
```

**Say:**
> "If you have an Anthropic API key, Claude writes the executive summary,
> recommendations, and next experiments.
> Without the key, SERA uses structured fallback generators —
> the report is always complete."

---

### Closing (30 seconds)

> "That's the full SERA research cycle.
>
> One brief. Three hypotheses. One experiment. Two conditions.
> One winner. One client-ready report.
>
> Everything is Markdown. Everything lives in your vault.
> Everything is reproducible.
>
> SERA Vault OS was built entirely by Claude Code agents in parallel git worktrees,
> with Nemp Memory as the shared brain between sessions.
> Four agents. Zero conflicts. One integrated system."

Show the git log:
```bash
git log --oneline
```

```
bd73406  fix+chore: integration fix, full test suite green, E2E verified
14fc29b  merge(session-4): integrate reports/ module into master
4ba455c  merge(session-3): integrate engine/ module into master
0a7df48  merge(session-1): integrate cli/ module into master
91c2534  merge(session-2): integrate vault/ module into master
...
d87427a  feat(session-0): scaffold SERA Vault OS shared foundation
```

> "79 tests. 7 workflow steps verified. All green."

---

## Live Demo Checklist

Before recording or presenting, run through this checklist:

- [ ] `pip install -r requirements.txt` — all dependencies installed
- [ ] `python -m cli.main --version` — CLI responds correctly
- [ ] `python -m pytest tests/ -q` — 79 passed
- [ ] Brief file `vault/clients/acme-corp/briefs/brief-001.md` written and ready
- [ ] (Optional) `ANTHROPIC_API_KEY` set for AI-powered generation
- [ ] Terminal font size readable at recording resolution
- [ ] Obsidian open and pointing at `vault/clients/acme-corp/` (optional, for visual)

---

## Pre-Written Demo Brief

Copy this into `vault/clients/acme-corp/briefs/brief-001.md` before the demo:

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

## Background

Current onboarding has 7 steps. Drop-off analysis shows 60% of trials
abandon at step 4 (team invite). Hypothesis: the flow is too complex
for solo founders who are our primary ICP.

## Target Audience

Solo founders and small teams (1-5 people) in SaaS.

## Research Questions

1. What are the top three friction points in the onboarding flow?
2. Which onboarding steps correlate most strongly with paid conversion?
3. Does simplifying to 3 steps improve conversion without hurting activation quality?

## Timeline

Two-week sprint. Results by 2026-05-26.
```

---

## One-Liner Positioning

> SERA Vault OS is the research operating system for founders who run experiments
> the same way engineers ship code — structured, version-controlled, and repeatable.

---

## Key Numbers for the Demo

| Metric | Value |
|--------|-------|
| Sessions built in parallel | 4 |
| Git worktrees used | 4 |
| Lines of Python | ~1,200 |
| Automated tests | 79 |
| E2E workflow steps | 7 |
| Integration bugs found | 1 (CLI subfolder mismatch) |
| Integration bugs remaining | 0 |

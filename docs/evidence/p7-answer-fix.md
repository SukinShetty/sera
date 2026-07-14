# P7 — Metric-Aware ANSWER Synthesis (Trust-Critical Fix)

**Date:** 2026-07-14
**Scope:** `cli/commands/ask.py` answer synthesis only. The report
generator was already correct and was not touched.

## The bug

The ANSWER panel's headline could contradict its own evidence table. The
old `_condition_vote` counted **how many experiments each condition won**,
then broke ties by margin/alphabetical order — it never looked at the
actual metric values. For "which method finds duplicate customer records
best," two experiments both measured **f1_score**, each had a different
winner, so the vote tied 1–1 and the tiebreak crowned the objectively
worse condition:

```
OLD (condition-vote): 'fuzzy_matching' won 1 of 3 (margin 1.0)
```

That headline named `fuzzy_matching` (f1_score **0.2102**) as the answer
while the evidence table right below it showed `combined_..._pipeline` at
f1_score **0.8696** — a 4× better score on the *same metric*. A research
tool whose headline disagrees with its own numbers is untrustworthy.

## The fix

`_synthesize_answer` replaces the blind vote with metric-aware logic. The
governing rule: **same metric name = commensurable scale (compare values
directly); different metric names = incommensurable (never compare raw
values).**

1. **Shared-metric path.** Group succeeded experiments by metric name. If
   one metric is the *unique* most-common and is shared by ≥2 experiments,
   the answer is the condition with the highest actual value on that
   metric. (Each experiment's winner is its own max, so the top winner
   value is the true maximum across all conditions on that metric.)
2. **Different-metric path.** If no metric is shared across ≥2 experiments
   (or several tie for most-common), the metrics are incommensurable. Do
   **not** crown a single value winner. Fall back to counting experiment
   wins and say so honestly.
3. **Degenerate guard (`_guard_same_metric`).** In the vote path, a
   condition can never be crowned while a condition sharing its metric
   scored strictly higher — an explicit safety net against the same class
   of bug leaking through the vote path.
4. **Never** compare raw values across different metric names (the inverse
   bug — e.g. crowning `sla_compliance=100.0` over `recovery_rate=202.9`).

`_condition_vote` is unchanged and retained as the vote primitive; its
existing tests still pass.

## Re-run: the three saved questions

These panels are re-rendered by the new synthesis over the **real saved
experiment results** (reconstructed from each client's `results/*.md`; no
experiments were re-executed — the bug was in synthesis, not measurement).

### 1. Dedup — the reported bug, now fixed (shared-metric path)

`ask-method-finds-duplicate-customer` — *"Which method finds duplicate
customer records best: exact match or fuzzy matching...?"*

Evidence: two experiments share **f1_score** (fuzzy 0.2102, combined
0.8696); a third measures precision.

**Before:** `fuzzy_matching won 1 of 3` — the 0.2102 condition.
**After:**

```
+---------------------------------- ANSWER ----------------------------------+
| combined_exact_then_fuzzy_pipeline — best f1_score at 0.8696 (compared     |
| across 2 experiments sharing this metric)                                  |
|                                                                            |
| Question: Which method finds duplicate customer records best: exact ...    |
+----------------------------------------------------------------------------+
        Evidence: 3/3 experiments succeeded
 Hypothesis                  Winner                    Metric     Value
 Fuzzy Matching Catches...   fuzzy_matching            f1_score   0.2102
 Exact Matching Produces...  exact_matching            precision  1.0
 Combined Pipeline Out...    combined_..._pipeline*    f1_score   0.8696   <- highlighted
```

The headline now agrees with the evidence: the 0.8696 condition wins on
the shared metric. `precision=1.0` is *not* compared against the f1_score
values (different metric).

### 2. Retry — incommensurable metrics, honest path (different-metric)

`ask-retry-approach-recovers-fastest` — *"Which retry approach recovers
fastest after a failure...?"*

The three experiments used three different metrics
(`recovery_rate_per_second`, `recovery_efficiency_score`,
`sla_compliance_rate_pct`). Their raw values (202.9, 18.19, 100.0) are
**not comparable**, so no single value winner is crowned:

```
+---------------------------------- ANSWER ----------------------------------+
| Experiments used different metrics; no single comparable winner. By        |
| experiment wins: immediate_retry won 2 of 3.                               |
|                                                                            |
| Question: Which retry approach recovers fastest after a failure: ...       |
+----------------------------------------------------------------------------+
 Hypothesis              Winner              Metric                      Value
 Immediate Retry Wins... immediate_retry     recovery_rate_per_second    202.9261
 Exponential Backoff...  exponential_backoff recovery_efficiency_score   18.19
 Fixed Delay Offers...   immediate_retry     sla_compliance_rate_pct     100.0
```

Honest framing: it reports `immediate_retry` leads *by experiment wins*
(2 of 3), and explicitly states the metrics differ — it never claims a
comparable-value victory across incommensurable scales.

### 3. JSON robustness — clean shared-metric win

`ask-json-parsing-approach-robust` — *"Which JSON parsing approach is most
robust to malformed input...?"*

Two experiments share `composite_robustness_score` (stdlib 100.0 vs
manual_slicing 40.06); a third uses a differently-named `robustness_score`
(69.0), which is correctly **not** compared against the 100.0 scale
despite the similar name:

```
+---------------------------------- ANSWER ----------------------------------+
| stdlib_json_try_except — best composite_robustness_score at 100.0          |
| (compared across 2 experiments sharing this metric)                        |
|                                                                            |
| Question: Which JSON parsing approach is most robust to malformed ...      |
+----------------------------------------------------------------------------+
 Hypothesis                Winner                  Metric                       Value
 Stdlib JSON try/except..  stdlib_json_try_except  composite_robustness_score   100.0  <- highlighted
 Regex extraction...       manual_slicing          composite_robustness_score   40.06
 Manual slicing fails...   manual_string_slicing   robustness_score             69.0
```

## Tests

`tests/test_answer_synthesis.py` (no API) covers all four required cases:

- **a. dedup:** two experiments share f1_score (0.2102 vs 0.8696) → answer
  MUST be `combined_pipeline` (0.8696), never fuzzy.
- **b. retry:** three different metrics → different-metric vote path;
  reports no value, never compares raw values across metrics.
- **c. degenerate guard:** a condition that won its experiment at a lower
  same-metric value than another is NOT crowned (switches to the higher).
- **d. clean shared-metric:** highest value on the shared metric wins.

`tests/test_memory.py::TestConditionVote` (the untouched vote primitive)
continues to pass.

Full suite tail (`py -3.14 -m pytest -q`):

```
........................................................................ [ 49%]
........................................................................ [ 99%]
.                                                                        [100%]
145 passed in 115.15s (0:01:55)
```

That is the prior 138 green plus the 7 new answer-synthesis tests.

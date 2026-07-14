"""
engine/ablation.py — Memory ablation harness for SERA.

Tests the architecture's core claim: does accumulated research memory
measurably improve hypothesis quality? Metric: Hypothesis Survival Rate
(HSR) = survived / (survived + killed) — failures are excluded as
infrastructure noise.

Public API:
    run_ablation(briefs_path, cycles=3, repeats=1, memory_arms=("on", "off"),
                 out_dir=None, dry_run=False, timeout=300, progress=None) -> dict

Design:
    - Each arm × repeat gets an ISOLATED ledger file (via SERA_LEDGER_PATH)
      and its own client vault, so arms never contaminate each other and
      memory-off truly starts cold every repeat.
    - Both arms RECORD outcomes (verdicts require it); only the "on" arm
      READS memory during hypothesis generation.
    - Cycles run the full brief set repeatedly: in the "on" arm, cycle N
      generates hypotheses conditioned on cycles 1..N-1's outcomes.
    - dry_run=True replaces the Claude-dependent steps (hypothesis prompt,
      script generation/execution) with a deterministic offline mock while
      exercising IDENTICAL bookkeeping: brief writes, memory query/injection
      + audit logs, ledger records, results.jsonl, summary, chart.

Outputs in out_dir (default experiments/ablation/runs/<UTC timestamp>/):
    results.jsonl        one row per hypothesis outcome
    summary.json         HSR per arm per cycle (mean ± std across repeats)
    ablation_curve.png   the memory-on vs memory-off HSR curve
    ablation_curve.csv   long-format data for re-plotting
    ledger-<arm>-r<n>.jsonl   each arm×repeat's isolated ledger
"""

import csv
import hashlib
import json
import os
import statistics
from datetime import date, datetime, timezone
from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir, read_markdown, write_markdown

HYPOTHESES_PER_BRIEF = 3


def run_ablation(
    briefs_path,
    cycles: int = 3,
    repeats: int = 1,
    memory_arms: tuple = ("on", "off"),
    out_dir=None,
    dry_run: bool = False,
    timeout: int = 300,
    progress=None,
) -> dict:
    """
    Run the memory ablation experiment. Returns the summary dict (also
    written to out_dir/summary.json) with an added "paths" section.
    """
    briefs = _load_briefs(briefs_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(out_dir) if out_dir else PROJECT_ROOT / "experiments" / "ablation" / "runs" / stamp
    ensure_dir(out)
    say = progress or (lambda message: None)

    # INTERLEAVED arm ordering (run-2 fix, docs/evidence/p6.md): within every
    # cycle+brief, run all arm×repeat combinations back-to-back so any
    # wall-clock event (billing, throttling, outage) hits every arm
    # symmetrically instead of landing entirely on whichever arm ran last.
    # Cycle stays the OUTERMOST loop, so an arm's full cycle N completes
    # before its cycle N+1 begins — required for memory-conditioning validity.
    arm_repeats = [(arm, repeat)
                   for repeat in range(1, repeats + 1)
                   for arm in memory_arms]

    results = []
    previous_ledger = os.environ.get("SERA_LEDGER_PATH")
    try:
        for cycle in range(1, cycles + 1):
            for brief in briefs:
                for arm, repeat in arm_repeats:
                    ledger_path = out / f"ledger-{arm}-r{repeat}.jsonl"
                    # client is derived from out_dir (unique per run), so every
                    # run gets fresh vaults and hypothesis numbering starts at
                    # hyp-001 and continues per (arm, repeat) across cycles.
                    client = f"ablation-{out.name.lower()}-{arm}-r{repeat}"
                    # switch the isolated ledger PER ASK so interleaved arms
                    # never read or write each other's memory.
                    os.environ["SERA_LEDGER_PATH"] = str(ledger_path)
                    say(f"cycle={cycle}/{cycles} brief={brief['id']} "
                        f"-> arm={arm} r{repeat} [interleaved]")
                    for row in _run_brief(client, brief, arm == "on", dry_run, timeout, repeat):
                        row = {"arm": arm, "repeat": repeat, "cycle": cycle,
                               "brief_id": brief["id"], **row}
                        results.append(row)
                        _append_jsonl(out / "results.jsonl", row)
    finally:
        if previous_ledger is None:
            os.environ.pop("SERA_LEDGER_PATH", None)
        else:
            os.environ["SERA_LEDGER_PATH"] = previous_ledger

    summary = summarize(results, cycles, repeats, memory_arms)
    summary["params"] = {
        "briefs": len(briefs),
        "cycles": cycles,
        "repeats": repeats,
        "arms": list(memory_arms),
        "dry_run": dry_run,
        "started_utc": stamp,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_path = _write_csv(summary, out / "ablation_curve.csv")
    png_path = render_curve(summary, out / "ablation_curve.png", repeats)

    summary["paths"] = {
        "out_dir": str(out),
        "results": str(out / "results.jsonl"),
        "summary": str(out / "summary.json"),
        "csv": str(csv_path),
        "png": str(png_path),
    }
    return summary


def hsr(survived: int, killed: int) -> float:
    """Hypothesis Survival Rate. Failures are excluded by construction."""
    decided = survived + killed
    return round(survived / decided, 4) if decided else 0.0


def summarize(results: list, cycles: int, repeats: int, memory_arms: tuple) -> dict:
    """Aggregate per-hypothesis rows into HSR per arm per cycle (mean ± std)."""
    arms = {}
    for arm in memory_arms:
        cycle_stats = []
        for cycle in range(1, cycles + 1):
            per_repeat = []
            for repeat in range(1, repeats + 1):
                rows = [r for r in results
                        if r["arm"] == arm and r["cycle"] == cycle and r["repeat"] == repeat]
                counts = _verdict_counts(rows)
                per_repeat.append({
                    "repeat": repeat,
                    "hsr": hsr(counts["survived"], counts["killed"]),
                    **counts,
                })
            values = [r["hsr"] for r in per_repeat]
            cycle_stats.append({
                "cycle": cycle,
                "hsr_mean": round(statistics.mean(values), 4) if values else 0.0,
                "hsr_std": round(statistics.pstdev(values), 4) if values else 0.0,
                **_verdict_counts([r for r in results if r["arm"] == arm and r["cycle"] == cycle]),
                "per_repeat": per_repeat,
            })
        arm_rows = [r for r in results if r["arm"] == arm]
        arm_counts = _verdict_counts(arm_rows)
        arms[arm] = {
            "cycles": cycle_stats,
            "overall_hsr": hsr(arm_counts["survived"], arm_counts["killed"]),
            **arm_counts,
        }
    return {"arms": arms}


def render_curve(summary: dict, png_path, repeats: int):
    """Render the HSR-per-cycle curve, one line per arm, error bands if repeats > 1."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    for arm, arm_data in summary["arms"].items():
        xs = [c["cycle"] for c in arm_data["cycles"]]
        means = [c["hsr_mean"] for c in arm_data["cycles"]]
        stds = [c["hsr_std"] for c in arm_data["cycles"]]
        line, = ax.plot(xs, means, marker="o", label=f"memory-{arm}")
        if repeats > 1:
            ax.fill_between(
                xs,
                [m - s for m, s in zip(means, stds)],
                [m + s for m, s in zip(means, stds)],
                alpha=0.2,
                color=line.get_color(),
            )

    ax.set_title("Hypothesis Survival Rate: memory-on vs memory-off")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("HSR = survived / (survived + killed)")
    ax.set_ylim(0.0, 1.0)
    ax.set_xticks(sorted({c["cycle"] for a in summary["arms"].values() for c in a["cycles"]}))
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return Path(png_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_brief(client: str, brief: dict, memory: bool, dry_run: bool, timeout: int, repeat: int) -> list:
    """
    Run one brief through the ask pipeline for one arm. Returns one row per
    hypothesis: {hypothesis_id, predicted_winner, actual_winner, verdict}.
    Both real and dry-run modes share all bookkeeping (brief write, memory
    query + audit log, ledger record); dry-run only swaps the Claude steps.
    """
    from engine import ledger
    from engine.api import BillingError
    from engine.experiment import create as create_experiment
    from engine.hypothesis import generate as generate_hypotheses
    from engine.scriptgen import generate_script

    clients_root = PROJECT_ROOT / CONFIG["paths"]["clients_root"]
    client_root = clients_root / client
    for sub in ("briefs", "hypotheses", "experiments", "results"):
        ensure_dir(client_root / sub)

    vault_brief_id = _write_brief(client_root, client, brief["question"])

    if dry_run:
        # No Claude: force the offline fallback generator, but keep the
        # memory flag live so ledger.query + the hypgen audit log run
        # exactly as they would in a real arm. (strict is irrelevant offline —
        # the fallback IS the intended path here.)
        key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            hyp_ids = generate_hypotheses(client, vault_brief_id, memory=memory)
        finally:
            if key is not None:
                os.environ["ANTHROPIC_API_KEY"] = key
    else:
        # strict=True: a memory-off ask must never be silently backfilled by
        # the offline template generator (that confounded run 1). A billing
        # error aborts the whole run; any other hypgen failure fails only
        # this brief's asks and lets the run continue.
        try:
            hyp_ids = generate_hypotheses(client, vault_brief_id, memory=memory, strict=True)
        except BillingError:
            raise
        except Exception:  # noqa: BLE001 — hypgen failed for this brief
            return [_failed_row() for _ in range(HYPOTHESES_PER_BRIEF)]

    rows = []
    for hyp_id in hyp_ids[:HYPOTHESES_PER_BRIEF]:
        hyp_fm, _ = read_markdown(client_root / "hypotheses" / f"{hyp_id}.md")
        predicted = hyp_fm.get("predicted_winner", "")
        title = hyp_fm.get("title", hyp_id)

        summary = None
        if dry_run:
            summary = _mock_run("on" if memory else "off", repeat, brief["id"], hyp_id, predicted)
        else:
            try:
                exp_id = create_experiment(client, hyp_id)
                summary = generate_script(client, exp_id, timeout=timeout)
            except BillingError:
                # unrecoverable credit exhaustion — abort the ENTIRE run
                # rather than record a bogus "failed" verdict.
                raise
            except Exception:  # noqa: BLE001 — a failed experiment is a "failed" verdict
                summary = None

        actual = summary["winner"]["winner_condition"] if summary else None
        verdict = ledger.compute_verdict(predicted, actual)
        ledger.record({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "client": client,
            "brief_id": vault_brief_id,
            "question": brief["question"],
            "hypothesis_id": hyp_id,
            "hypothesis_title": title,
            "predicted_winner": predicted,
            "actual_winner": actual,
            "verdict": verdict,
            "metric": summary["metric"] if summary else None,
            "winner_value": summary["winner"]["winner_value"] if summary else None,
            "conditions": summary["conditions"] if summary else None,
            "mode": summary["mode"] if summary else None,
            "attempts": summary["attempts"] if summary else None,
        })
        rows.append({
            "hypothesis_id": hyp_id,
            "predicted_winner": predicted,
            "actual_winner": actual,
            "verdict": verdict,
        })
    return rows


def _failed_row() -> dict:
    """A result row for an ask whose hypotheses could not be generated."""
    return {"hypothesis_id": "", "predicted_winner": "",
            "actual_winner": None, "verdict": "failed"}


def _mock_run(arm: str, repeat: int, brief_id: str, hyp_id: str, predicted: str):
    """
    Deterministic dry-run stand-in for scriptgen.generate_script: verdicts
    derive from a stable hash of (arm, repeat, brief, hypothesis, prediction)
    — never of anything timestamped — so identical params reproduce identical
    results, while repeats still differ enough to exercise the mean/std and
    error-band machinery. Roughly 40% survived / 50% killed / 10% failed.
    """
    digest = int(hashlib.md5(
        f"{arm}|r{repeat}|{brief_id}|{hyp_id}|{predicted}".encode("utf-8")
    ).hexdigest()[:8], 16) % 10

    if digest == 9:
        return None  # experiment "failed"
    survived = digest <= 3
    actual = predicted if survived else f"rival_of_{predicted}"
    return {
        "metric": "mock_score",
        "conditions": {predicted: 0.9 if survived else 0.4,
                       f"rival_of_{predicted}": 0.4 if survived else 0.9},
        "winner": {"winner_condition": actual, "winner_value": 0.9},
        "mode": "simulation",
        "attempts": 1,
    }


def _load_briefs(briefs_path) -> list:
    path = Path(briefs_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(
            f"\n[SERA Ablation] Briefs file not found:\n  {path}\n"
            "Each line must be JSON: {\"id\": ..., \"question\": ...}"
        )
    briefs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            briefs.append(json.loads(line))
    if not briefs:
        raise ValueError(f"\n[SERA Ablation] Briefs file is empty: {path}")
    return briefs


def _write_brief(client_root, client: str, question: str) -> str:
    briefs_dir = client_root / "briefs"
    existing = sorted(briefs_dir.glob("brief-*.md"))
    brief_id = f"brief-{len(existing) + 1:03d}"
    title = question if len(question) <= 80 else question[:77] + "..."
    write_markdown(
        briefs_dir / f"{brief_id}.md",
        body=f"# Research Brief: {title}\n\n## Objective\n\n{question}\n",
        frontmatter={
            "title": title,
            "client_id": client,
            "status": "active",
            "created": date.today().isoformat(),
        },
    )
    return brief_id


def _append_jsonl(path, row: dict) -> None:
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _verdict_counts(rows: list) -> dict:
    return {
        "survived": sum(1 for r in rows if r["verdict"] == "survived"),
        "killed": sum(1 for r in rows if r["verdict"] == "killed"),
        "failed": sum(1 for r in rows if r["verdict"] == "failed"),
    }


def _write_csv(summary: dict, csv_path):
    with Path(csv_path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["arm", "cycle", "repeat", "hsr", "survived", "killed", "failed"])
        for arm, arm_data in summary["arms"].items():
            for cycle_stat in arm_data["cycles"]:
                for rep in cycle_stat["per_repeat"]:
                    writer.writerow([
                        arm, cycle_stat["cycle"], rep["repeat"], rep["hsr"],
                        rep["survived"], rep["killed"], rep["failed"],
                    ])
    return Path(csv_path)

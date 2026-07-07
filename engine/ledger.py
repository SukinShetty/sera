"""
engine/ledger.py — Append-only outcome ledger for SERA's research memory.

Every completed (or failed) generated experiment is recorded here so future
hypothesis generation can calibrate on what actually happened.

Storage: JSONL at vault/ledger.jsonl — one entry per line, append-only.
The path can be overridden via the SERA_LEDGER_PATH environment variable;
the ablation harness uses this to give each arm×repeat an isolated ledger
so memory arms never contaminate each other.

Public API:
    record(entry: dict) -> None
        Append one outcome entry to the ledger.

    query(question: str, k: int = 5) -> list[dict]
        The k most relevant past outcomes, scored by token overlap between
        the question and each entry's stored question + hypothesis title.
        Zero-overlap entries are never returned.

    stats() -> dict
        Totals, verdict counts, survival_rate (survived / (survived+killed),
        failures excluded), and per-client counts.

    compute_verdict(predicted_winner, actual_winner) -> str
        "failed" if there is no actual winner (experiment errored),
        "survived" if the prediction matched (case-insensitive), else "killed".

Entry schema:
    {ts, client, brief_id, question, hypothesis_id, hypothesis_title,
     predicted_winner, actual_winner, verdict, metric, winner_value,
     conditions, mode, attempts}
"""

import json
import os
import string
from pathlib import Path

from shared.config import CONFIG, PROJECT_ROOT
from shared.file_io import ensure_dir

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "by", "do", "does", "for", "from",
    "how", "in", "is", "it", "its", "of", "on", "or", "the", "to", "what",
    "when", "where", "which", "who", "with", "most", "more",
}


def record(entry: dict) -> None:
    """Append one outcome entry to the ledger (creates the file if needed)."""
    path = _ledger_path()
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def query(question: str, k: int = 5) -> list:
    """
    Return the k past outcomes most relevant to `question`.

    Relevance = number of shared tokens (lowercased, punctuation stripped,
    stopwords removed) between the question and the entry's stored
    question + hypothesis_title. Ties keep ledger (chronological) order.
    """
    question_tokens = _tokens(question)
    scored = []
    for i, entry in enumerate(_read_all()):
        text = f"{entry.get('question', '')} {entry.get('hypothesis_title', '')}"
        overlap = len(question_tokens & _tokens(text))
        if overlap > 0:
            scored.append((-overlap, i, entry))
    scored.sort()
    return [entry for _, _, entry in scored[:k]]


def stats() -> dict:
    """Aggregate ledger statistics."""
    entries = _read_all()
    counts = {"survived": 0, "killed": 0, "failed": 0}
    by_client = {}
    for entry in entries:
        verdict = entry.get("verdict", "")
        if verdict in counts:
            counts[verdict] += 1
        client = entry.get("client", "unknown")
        by_client[client] = by_client.get(client, 0) + 1

    decided = counts["survived"] + counts["killed"]
    return {
        "total": len(entries),
        "survived": counts["survived"],
        "killed": counts["killed"],
        "failed": counts["failed"],
        "survival_rate": round(counts["survived"] / decided, 4) if decided else 0.0,
        "by_client": by_client,
    }


def compute_verdict(predicted_winner, actual_winner) -> str:
    """Verdict for one hypothesis: survived / killed / failed."""
    if not actual_winner:
        return "failed"
    if str(predicted_winner).strip().lower() == str(actual_winner).strip().lower():
        return "survived"
    return "killed"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ledger_path():
    override = os.environ.get("SERA_LEDGER_PATH")
    if override:
        return Path(override)
    return PROJECT_ROOT / CONFIG["paths"]["vault_root"] / "ledger.jsonl"


def _read_all() -> list:
    path = _ledger_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # never let one corrupt line poison the whole memory
    return entries


def _tokens(text: str) -> set:
    table = str.maketrans("", "", string.punctuation)
    return {
        w for w in str(text).lower().translate(table).split()
        if w and w not in STOPWORDS
    }

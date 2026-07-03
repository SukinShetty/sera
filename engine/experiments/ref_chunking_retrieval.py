"""
engine/experiments/ref_chunking_retrieval.py — SERA reference experiment.

A real, fully deterministic retrieval experiment: it compares three document
chunking strategies (small fixed-size windows, large fixed-size windows, and
paragraph-based chunks) on the same corpus and query set, scoring each
strategy by mean reciprocal rank (MRR) with length-normalized keyword
retrieval.

Runs standalone with no dependencies beyond the standard library:

    python ref_chunking_retrieval.py

Output contract (consumed by engine.runner):
    - exits 0 on success
    - the FINAL stdout line is:
        SERA_METRICS {"metric": "mrr", "conditions": {...}}
"""

import json
import string
import sys

# ---------------------------------------------------------------------------
# Corpus — four short knowledge-base articles, multiple paragraphs each.
# ---------------------------------------------------------------------------

CORPUS = {
    "onboarding": (
        "The onboarding flow starts with an email signup form and a short "
        "survey about team size and primary use case. Users who skip the "
        "survey are routed to a generic template gallery instead of a "
        "personalized workspace.\n\n"
        "Activation is defined as creating a first project and inviting at "
        "least one teammate within seven days. Cohort analysis shows that "
        "users who reach activation retain at three times the baseline rate.\n\n"
        "The biggest drop-off happens on the workspace configuration step, "
        "where users must choose integrations before seeing any value. Moving "
        "integration setup after the first project reduced abandonment in an "
        "earlier pilot."
    ),
    "pricing": (
        "The pricing page offers three tiers: Starter, Growth, and Scale. "
        "Starter is free forever with a cap of three projects and community "
        "support only.\n\n"
        "Growth is billed per seat per month and unlocks unlimited projects, "
        "priority support, and the analytics dashboard. Annual billing "
        "carries a twenty percent discount over monthly billing.\n\n"
        "Scale is a custom contract with single sign-on, audit logs, and a "
        "dedicated success manager. Enterprise procurement usually asks for "
        "a security questionnaire before the contract is signed."
    ),
    "search_infra": (
        "The search service indexes documents into an inverted index that is "
        "rebuilt incrementally every five minutes. Tokenization lowercases "
        "text, strips punctuation, and removes a small stopword list.\n\n"
        "Ranking combines term frequency with a length penalty so that very "
        "long documents do not dominate the results purely by repeating "
        "keywords. Ties are broken by document recency.\n\n"
        "Query latency is served from an in-memory cache with a five minute "
        "expiry. Cache misses fall back to the index shard closest to the "
        "user's region."
    ),
    "support": (
        "Support tickets arrive through email, in-app chat, and the public "
        "community forum. Every ticket is triaged into billing, bug report, "
        "or how-to within one business hour.\n\n"
        "Billing tickets are escalated directly to the finance rotation, "
        "while bug reports get a reproduction attempt before engineering "
        "handoff. How-to questions are answered from the knowledge base "
        "first.\n\n"
        "The team tracks first response time and resolution time as its two "
        "service level objectives. Chat has the strictest target at fifteen "
        "minutes for first response."
    ),
}

# Each query names the document that actually answers it. Several queries
# deliberately reuse vocabulary that appears in more than one document
# (billing, email, minutes, projects, support, team) so ranking quality —
# not mere keyword presence — separates the chunking strategies.
QUERIES = [
    ("what counts as activation for a new user", "onboarding"),
    ("where do users abandon workspace configuration", "onboarding"),
    ("email signup form for new users", "onboarding"),
    ("team retention after the first project", "onboarding"),
    ("how much is the annual billing discount", "pricing"),
    ("project cap on the free tier", "pricing"),
    ("monthly billing per seat", "pricing"),
    ("support included with the free plan", "pricing"),
    ("how often is the index rebuilt in minutes", "search_infra"),
    ("ranking penalty for long documents repeating keywords", "search_infra"),
    ("cache expiry for query results", "search_infra"),
    ("first response target in minutes for chat", "support"),
    ("billing ticket escalation to finance", "support"),
    ("email tickets triaged by the team", "support"),
]

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
    "from", "how", "in", "is", "it", "its", "of", "on", "or", "the", "to",
    "what", "where", "which", "who", "with",
}


# ---------------------------------------------------------------------------
# Chunking strategies (the experimental conditions)
# ---------------------------------------------------------------------------

def chunk_fixed(text: str, size: int) -> list:
    """Split text into consecutive fixed-size word windows."""
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def chunk_paragraph(text: str) -> list:
    """Split text on blank lines — one chunk per paragraph."""
    return [p.strip() for p in text.split("\n\n") if p.strip()]


CONDITIONS = {
    "fixed_32_words": lambda text: chunk_fixed(text, 32),
    "fixed_128_words": lambda text: chunk_fixed(text, 128),
    "paragraph": chunk_paragraph,
}


# ---------------------------------------------------------------------------
# Retrieval and evaluation
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list:
    """Lowercase, strip punctuation, drop stopwords."""
    table = str.maketrans("", "", string.punctuation)
    return [
        w for w in text.lower().translate(table).split()
        if w and w not in STOPWORDS
    ]


def score(query_terms: set, chunk_tokens: list) -> float:
    """Length-normalized term-frequency overlap."""
    if not chunk_tokens:
        return 0.0
    hits = sum(1 for token in chunk_tokens if token in query_terms)
    return hits / len(chunk_tokens)


def evaluate(chunker) -> float:
    """Mean reciprocal rank of the first chunk from the relevant document."""
    # Build the chunk index deterministically: corpus order, then chunk order.
    index = []
    for doc_id, text in CORPUS.items():
        for i, chunk in enumerate(chunker(text)):
            index.append((doc_id, i, tokenize(chunk)))

    reciprocal_ranks = []
    for query, relevant_doc in QUERIES:
        query_terms = set(tokenize(query))
        ranked = sorted(
            index,
            key=lambda entry: (-score(query_terms, entry[2]), entry[0], entry[1]),
        )
        rank = next(
            (pos for pos, (doc_id, _, _) in enumerate(ranked, 1) if doc_id == relevant_doc),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

    return round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4)


def main() -> int:
    print("Reference experiment: chunking strategy vs retrieval MRR")
    print(f"Corpus: {len(CORPUS)} documents | Queries: {len(QUERIES)}")

    results = {}
    for name, chunker in CONDITIONS.items():
        mrr = evaluate(chunker)
        results[name] = mrr
        print(f"  condition={name:<16} mrr={mrr}")

    print(METRICS_LINE_HELP)
    print(f"SERA_METRICS {json.dumps({'metric': 'mrr', 'conditions': results})}")
    return 0


METRICS_LINE_HELP = "Emitting SERA_METRICS contract line:"


if __name__ == "__main__":
    sys.exit(main())

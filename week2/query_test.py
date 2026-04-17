"""
week2/query_test.py — Test runner for the AppMentor knowledge base.

Runs 12 predefined queries (9 general + 3 code-commentary) covering all
ERPNext modules and prints plain-text relevance labels based on cosine distance.

Relevance thresholds (cosine distance, lower = more similar):
    High   : distance < 0.3
    Medium : distance < 0.5
    Low    : distance >= 0.5

NOTE: No ANSI colour codes are used — plain text only, safe on Windows
PowerShell which does not reliably render ANSI escape sequences.

Usage
-----
    python week2/query_test.py                        # run all 9 test queries
    python week2/query_test.py --query "How do I..."  # single query
    python week2/query_test.py --interactive          # live Q&A mode (Ctrl+C to exit)
    python week2/query_test.py --n 5                  # top-5 results per query
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import CONFIG
from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# Relevance thresholds
# ---------------------------------------------------------------------------

_HIGH_THRESHOLD   = 0.3   # distance < 0.3  → High
_MEDIUM_THRESHOLD = 0.5   # distance < 0.5  → Medium
                           # distance >= 0.5 → Low


def _label(distance: float) -> str:
    if distance < _HIGH_THRESHOLD:
        return "High  "
    if distance < _MEDIUM_THRESHOLD:
        return "Medium"
    return "Low   "


# ---------------------------------------------------------------------------
# 9 predefined test queries
# ---------------------------------------------------------------------------

TEST_QUERIES: list[str] = [
    # Original 9 — general ERPNext knowledge
    "How do I submit an expense claim?",
    "What happens if my leave approver is on leave?",
    "How do I approve a purchase order?",
    "Where can I check my leave balance?",
    "How is overtime calculated in payroll?",
    "How do I transfer stock between warehouses?",
    "What is the difference between invoice and delivery note?",
    "How do I reset my ERPNext password?",
    "How do I log time against a project?",
    # Code commentary — tests AI-generated function explanations
    "What business rules does the leave approval process follow?",
    "What validations exist when submitting an expense claim?",
    "What does the payroll calculation function do?",
]


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def _print_result_block(query: str, results: list[dict], n: int) -> None:
    print(f"\nQuery: {query}")
    print("-" * 72)

    if not results:
        print("  (no results — run: python week2/ingest.py --source forum)")
        return

    for i, r in enumerate(results[:n], 1):
        dist     = r["distance"]
        label    = _label(dist)
        source   = r["metadata"].get("source", "?")
        text     = r["text"].replace("\n", " ")[:120]

        print(f"  [{i}] Relevance: {label}  Distance: {dist:.3f}  Source: {source}")
        print(f"       {text}")

    print()


def _make_store() -> ChromaStore:
    return ChromaStore(
        persist_dir=CONFIG["chroma_persist_dir"],
        collection_name=CONFIG["collection_name"],
        embedding_model=CONFIG["embedding_model"],
    )


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def run_all_tests(store: ChromaStore, n: int) -> None:
    print("\nAppMentor Knowledge Base — Query Test Suite")
    print(f"Running {len(TEST_QUERIES)} queries, top-{n} results each")
    print(
        f"Relevance:  High (dist < {_HIGH_THRESHOLD})  "
        f"Medium (dist < {_MEDIUM_THRESHOLD})  "
        f"Low (dist >= {_MEDIUM_THRESHOLD})"
    )

    pass_count = 0
    fail_queries: list[str] = []

    for query in TEST_QUERIES:
        results = store.query(query, n_results=n)
        _print_result_block(query, results, n)

        # Check if top result is at least Medium relevance
        if results and results[0]["distance"] < _MEDIUM_THRESHOLD:
            pass_count += 1
        else:
            fail_queries.append(query)

    print("=" * 72)
    print(f"Summary: {pass_count}/{len(TEST_QUERIES)} queries scored High or Medium relevance")
    if fail_queries:
        print("Low relevance (may need more data):")
        for q in fail_queries:
            print(f"  - {q}")
    print()


def run_single_query(store: ChromaStore, query: str, n: int) -> None:
    results = store.query(query, n_results=n)
    _print_result_block(query, results, n)


def interactive_mode(store: ChromaStore, n: int) -> None:
    print("\nAppMentor KB — Interactive Query Mode")
    print("Type your question and press Enter. Press Ctrl+C to exit.\n")
    try:
        while True:
            try:
                query = input("Ask AppMentor: ").strip()
            except EOFError:
                break
            if not query:
                continue
            if query.lower() in {"exit", "quit"}:
                break
            results = store.query(query, n_results=n)
            _print_result_block(query, results, n)
    except KeyboardInterrupt:
        pass
    print("\nGoodbye!")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AppMentor KB query tester with plain-text relevance labels",
    )
    p.add_argument(
        "--query", "-q",
        help="Run a single query instead of the full test suite.",
    )
    p.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Enter interactive Q&A mode (Ctrl+C to exit).",
    )
    p.add_argument(
        "--n", "-n",
        type=int,
        default=3,
        help="Number of results per query (default: 3).",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    store = _make_store()
    total = store.count()
    print(f"Collection contains {total} chunk(s).")

    if total == 0:
        print(
            "\nCollection is empty. Populate it first:\n"
            "  python week2/ingest.py --source forum\n"
        )
        if not args.interactive:
            return

    if args.interactive:
        interactive_mode(store, args.n)
    elif args.query:
        run_single_query(store, args.query, args.n)
    else:
        run_all_tests(store, args.n)


if __name__ == "__main__":
    main()

"""
week2/query_test.py — Test runner for the AppMentor knowledge base.

Runs 9 predefined queries covering all ERPNext modules and prints
colour-coded relevance scores based on cosine distance:

    GREEN  (distance < 0.35) → highly relevant
    YELLOW (distance < 0.60) → somewhat relevant
    RED    (distance ≥ 0.60) → low relevance

Usage:
    python week2/query_test.py                        # run all 9 test queries
    python week2/query_test.py --query "How do I …"  # single query
    python week2/query_test.py --interactive          # REPL mode
    python week2/query_test.py --n 3                  # top-3 results per query
"""

import argparse
import sys
from pathlib import Path

# Ensure week2/ is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))

from config import GREEN_THRESHOLD, YELLOW_THRESHOLD
from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# ANSI colour helpers (works in most terminals; degrades gracefully on Windows)
# ---------------------------------------------------------------------------

RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _colour(distance: float) -> str:
    if distance < GREEN_THRESHOLD:
        return GREEN
    if distance < YELLOW_THRESHOLD:
        return YELLOW
    return RED


def _label(distance: float) -> str:
    if distance < GREEN_THRESHOLD:
        return "HIGH"
    if distance < YELLOW_THRESHOLD:
        return "MED "
    return "LOW "


# ---------------------------------------------------------------------------
# Predefined test queries (one per ERPNext module)
# ---------------------------------------------------------------------------

TEST_QUERIES: list[tuple[str, str]] = [
    ("hr", "How do I add a new employee to the system?"),
    ("hr", "What is the process to apply for annual leave?"),
    ("expense", "How do employees submit expense reimbursements?"),
    ("payroll", "How do I generate salary slips at month end?"),
    ("buying", "Steps to raise a purchase order for a supplier"),
    ("projects", "How do I track hours worked on a project?"),
    ("stock", "How do I move inventory between two warehouses?"),
    ("accounts", "How do I reconcile bank transactions?"),
    ("system", "How can an administrator reset a user password?"),
]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def print_results(query: str, results: list[dict], n: int) -> None:
    print(f"\n{BOLD}Query:{RESET} {query}")
    print("─" * 72)

    if not results:
        print("  (no results — is the collection empty? Run ingest.py first)")
        return

    for i, r in enumerate(results[:n], 1):
        dist = r["distance"]
        col = _colour(dist)
        label = _label(dist)
        meta = r["metadata"]
        module = meta.get("module", "?")
        source = meta.get("source", "?")

        # Trim document text for display
        text = r["text"].replace("\n", " ")
        if len(text) > 160:
            text = text[:157] + "…"

        print(
            f"  {col}[{label} dist={dist:.4f}]{RESET} "
            f"{DIM}[{source}/{module}]{RESET}\n"
            f"    {text}"
        )

    print()


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def run_all_tests(store: ChromaStore, n: int) -> None:
    print(f"\n{BOLD}AppMentor Knowledge Base — Query Test Suite{RESET}")
    print(f"Running {len(TEST_QUERIES)} queries, top-{n} results each\n")
    print(
        f"Relevance legend:  "
        f"{GREEN}GREEN  < {GREEN_THRESHOLD:.2f}{RESET}  "
        f"{YELLOW}YELLOW < {YELLOW_THRESHOLD:.2f}{RESET}  "
        f"{RED}RED ≥ {YELLOW_THRESHOLD:.2f}{RESET}"
    )

    for _module, query in TEST_QUERIES:
        results = store.query(query, n_results=n)
        print_results(query, results, n)


def run_single_query(store: ChromaStore, query: str, n: int) -> None:
    results = store.query(query, n_results=n)
    print_results(query, results, n)


def interactive_mode(store: ChromaStore, n: int) -> None:
    print(f"\n{BOLD}AppMentor KB — Interactive Query Mode{RESET}")
    print("Type your question and press Enter. Type 'exit' to quit.\n")
    while True:
        try:
            query = input("Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        results = store.query(query, n_results=n)
        print_results(query, results, n)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AppMentor KB query tester with colour-coded relevance scores",
    )
    p.add_argument("--query", "-q", help="Run a single query instead of the test suite.")
    p.add_argument(
        "--interactive", "-i", action="store_true", help="Enter interactive REPL mode."
    )
    p.add_argument(
        "--n", "-n", type=int, default=3, help="Number of results per query (default 3)."
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    store = ChromaStore()
    total = store.count()
    print(f"Collection contains {total} document(s).")

    if total == 0:
        print(
            "\nThe collection is empty. Run this first:\n"
            "  python week2/ingest.py --source forum\n"
        )

    if args.interactive:
        interactive_mode(store, args.n)
    elif args.query:
        run_single_query(store, args.query, args.n)
    else:
        run_all_tests(store, args.n)


if __name__ == "__main__":
    main()

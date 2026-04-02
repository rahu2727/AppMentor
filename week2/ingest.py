"""
week2/ingest.py — CLI entry point for building the AppMentor knowledge base.

Usage:
    python week2/ingest.py --source forum    # ingest forum Q&A pairs
    python week2/ingest.py --source docs     # ingest ERPNext docs (stub)
    python week2/ingest.py --source code     # ingest ERPNext source (stub)
    python week2/ingest.py --reset           # wipe the collection
    python week2/ingest.py --stats           # print collection statistics
    python week2/ingest.py --source forum --stats  # ingest then show stats
"""

import argparse
import importlib
import sys
from pathlib import Path

# Ensure week2/ is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))

from store.chroma_store import ChromaStore


# ---------------------------------------------------------------------------
# Source registry — add new sources here as the project grows
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: dict[str, str] = {
    "forum": "sources.forum_ingester",
    "docs": "sources.docs_ingester",    # stub — file doesn't exist yet
    "code": "sources.code_ingester",    # stub — file doesn't exist yet
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ingest_source(source: str, store: ChromaStore) -> None:
    module_path = SOURCE_REGISTRY.get(source)
    if module_path is None:
        print(f"  [SKIP] Unknown source '{source}'. Available: {list(SOURCE_REGISTRY)}")
        return

    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError:
        print(f"  [SKIP] Ingester for '{source}' not implemented yet ({module_path}).")
        return

    if not hasattr(mod, "get_documents"):
        print(f"  [SKIP] '{module_path}' has no get_documents() function.")
        return

    documents, metadatas, ids = mod.get_documents()
    print(f"  Ingesting {len(documents)} documents from source '{source}' …")
    store.add(documents, metadatas, ids)
    print(f"  Done. Collection now has {store.count()} total documents.")


def print_stats(store: ChromaStore) -> None:
    stats = store.stats()
    print(f"\nCollection statistics:")
    print(f"  Total documents : {stats['total']}")
    if stats["by_source"]:
        print("  By source:")
        for src, count in sorted(stats["by_source"].items()):
            print(f"    {src:15s} {count:4d}")
    else:
        print("  (collection is empty)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AppMentor knowledge-base ingestion CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python week2/ingest.py --source forum
  python week2/ingest.py --reset
  python week2/ingest.py --stats
  python week2/ingest.py --source forum --stats
""",
    )
    p.add_argument(
        "--source",
        choices=list(SOURCE_REGISTRY.keys()),
        help="Data source to ingest.",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Wipe all documents from the collection before ingesting.",
    )
    p.add_argument(
        "--stats",
        action="store_true",
        help="Print collection statistics (after any ingest/reset).",
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not any([args.source, args.reset, args.stats]):
        parser.print_help()
        sys.exit(0)

    store = ChromaStore()

    if args.reset:
        print("Resetting collection …")
        store.reset()
        print(f"  Collection wiped. Documents remaining: {store.count()}")

    if args.source:
        print(f"\nIngesting source: {args.source}")
        ingest_source(args.source, store)

    if args.stats:
        print_stats(store)


if __name__ == "__main__":
    main()

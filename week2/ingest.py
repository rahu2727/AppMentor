"""
week2/ingest.py — CLI entry point for building the AppMentor knowledge base.

Usage
-----
    python week2/ingest.py                      # run all available sources
    python week2/ingest.py --source forum       # forum Q&A only
    python week2/ingest.py --source docs        # crawl docs.erpnext.com
    python week2/ingest.py --reset              # wipe DB, then run all sources
    python week2/ingest.py --stats              # show stats and exit
    python week2/ingest.py --source forum --stats  # ingest then show stats
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path

# Make week2/ importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from config import CONFIG
from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------
# Maps CLI name -> dotted module path inside week2/
# Add new sources here as the project grows.

_SOURCE_REGISTRY: dict[str, str] = {
    "forum": "sources.forum_ingester",
    "docs":  "sources.docs_ingester",
    "code":  "sources.code_ingester",
}

_SOURCES_ALL = ["forum", "docs", "code"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store() -> ChromaStore:
    return ChromaStore(
        persist_dir=CONFIG["chroma_persist_dir"],
        collection_name=CONFIG["collection_name"],
        embedding_model=CONFIG["embedding_model"],
    )


def _ingest_source(source: str, store: ChromaStore) -> int:
    """
    Import and run one ingester. Returns chunks added (0 on skip/error).
    """
    module_path = _SOURCE_REGISTRY.get(source)
    if module_path is None:
        print(f"  [SKIP] Unknown source '{source}'.")
        return 0

    # Gracefully skip sources whose module file has not been created yet
    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError:
        print(f"  [SKIP] '{source}' ingester not built yet ({module_path}.py).")
        return 0
    except ImportError as exc:
        print(f"  [SKIP] '{source}' ingester failed to import: {exc}")
        return 0

    if not hasattr(mod, "run"):
        print(f"  [SKIP] '{module_path}' has no run() function.")
        return 0

    t0 = time.perf_counter()
    try:
        # docs ingester needs config; forum ingester does not — pass it safely
        import inspect
        sig = inspect.signature(mod.run)
        if len(sig.parameters) >= 2:
            added = mod.run(store, CONFIG)
        else:
            added = mod.run(store)
    except Exception as exc:
        print(f"  [ERROR] '{source}' ingester raised: {exc}")
        return 0

    elapsed = time.perf_counter() - t0
    print(f"  [{source}] {added} chunks added in {elapsed:.1f}s")
    return added


def _print_stats(store: ChromaStore) -> None:
    stats = store.stats()
    print("\nCollection statistics")
    print(f"  Total chunks : {stats['total']}")
    if stats["by_source"]:
        print("  By source    :")
        for src, count in sorted(stats["by_source"].items()):
            print(f"    {src:<15s}  {count:4d}")
    else:
        print("  (collection is empty)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AppMentor knowledge-base ingestion CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python week2/ingest.py                       # run forum + docs
  python week2/ingest.py --source forum        # forum only
  python week2/ingest.py --reset               # wipe then run all
  python week2/ingest.py --stats               # show stats and exit
""",
    )
    p.add_argument(
        "--source",
        choices=list(_SOURCE_REGISTRY.keys()),
        default=None,
        help="Data source to ingest. If omitted, runs forum and docs.",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Wipe the collection before ingesting.",
    )
    p.add_argument(
        "--stats",
        action="store_true",
        help="Print collection statistics (after any ingest/reset) and exit.",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Stats-only shortcut: no ingestion needed
    if args.stats and not args.source and not args.reset:
        store = _make_store()
        _print_stats(store)
        return

    print("AppMentor — Week 2 Ingestion Pipeline")
    print("=" * 40)

    store = _make_store()

    if args.reset:
        print("\nResetting collection...")
        store.reset()
        print(f"  Done. Chunks remaining: {store.count()}")

    sources_to_run = [args.source] if args.source else _SOURCES_ALL

    total_added = 0
    for source in sources_to_run:
        print(f"\nIngesting source: {source}")
        total_added += _ingest_source(source, store)

    print(f"\nIngestion complete. Total chunks added this run: {total_added}")
    print(f"Collection total: {store.count()} chunks")

    if args.stats:
        _print_stats(store)


if __name__ == "__main__":
    main()

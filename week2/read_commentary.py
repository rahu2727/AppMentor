"""
week2/read_commentary.py

Run from the project root:
    python week2/read_commentary.py

Queries ChromaDB for commentary chunks and prints them so you can
evaluate quality before committing to the full ingestion run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import CONFIG
from store.chroma_store import ChromaStore

store = ChromaStore(
    CONFIG["chroma_persist_dir"],
    CONFIG["collection_name"],
    CONFIG["embedding_model"],
)

print(f"Collection size: {store.count()} chunks\n")
print("=" * 60)

queries = [
    ("validate purchase order items", "buying/procurement"),
    ("how does leave approval work",  "HR/leave"),
    ("calculate payroll deductions",  "payroll"),
]

for query_text, label in queries:
    print(f"\nQuery: {query_text!r}  [{label}]")
    print("-" * 60)
    results = store.query(
        query_text,
        n_results=2,
        where={"chunk_type": {"$eq": "commentary"}},
    )
    if not results:
        print("  (no results)")
        continue
    for r in results:
        meta = r["metadata"]
        print(f"  Function : {meta.get('function_name', '?')}")
        print(f"  File     : {meta.get('file_path', '?')}")
        print(f"  Module   : {meta.get('module', '?')}")
        print(f"  Distance : {r['distance']:.4f}")
        print(f"  Expert   : {meta.get('expert_agent', '?')}")
        print()
        print(r["text"])
        print()
        print("- " * 30)

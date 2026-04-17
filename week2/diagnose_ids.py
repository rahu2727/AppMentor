"""
week2/diagnose_ids.py

Run from project root:
    python week2/diagnose_ids.py

Compares stored ChromaDB chunk IDs against what _commentary_id()
generates now, to expose path-format mismatches (e.g. Windows
backslash vs forward slash).
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import CONFIG
from store.chroma_store import ChromaStore


def _commentary_id(file_path: str, function_name: str) -> str:
    return hashlib.md5(
        f"commentary-{file_path}-{function_name}".encode("utf-8")
    ).hexdigest()


store = ChromaStore(
    CONFIG["chroma_persist_dir"],
    CONFIG["collection_name"],
    CONFIG["embedding_model"],
)

print(f"Total chunks in collection: {store.count()}\n")

# ── Step 1: show first 5 stored commentary IDs ───────────────────────────────
print("=" * 60)
print("STEP 1 — First 5 stored commentary chunk IDs")
print("=" * 60)

result = store._collection.get(
    where={"chunk_type": {"$eq": "commentary"}},
    limit=5,
    include=["metadatas"],
)

rows = list(zip(result["ids"], result["metadatas"]))
for stored_id, meta in rows:
    file_path = meta["file_path"]
    func_name = meta["function_name"]
    print(f"Stored ID : {stored_id}")
    print(f"File      : {file_path!r}")
    print(f"Func      : {func_name}")
    print()

# ── Step 2: regenerate IDs and compare ───────────────────────────────────────
print("=" * 60)
print("STEP 2 — Regenerated IDs (as-stored path vs normalised path)")
print("=" * 60)

for stored_id, meta in rows:
    file_path = meta["file_path"]
    func_name = meta["function_name"]
    normalised = file_path.replace("\\", "/")

    regen_raw  = _commentary_id(file_path,  func_name)
    regen_norm = _commentary_id(normalised, func_name)

    match_raw  = "MATCH" if regen_raw  == stored_id else "MISMATCH"
    match_norm = "MATCH" if regen_norm == stored_id else "MISMATCH"

    print(f"Func             : {func_name}")
    print(f"Stored path      : {file_path!r}")
    print(f"Normalised path  : {normalised!r}")
    print(f"Stored ID        : {stored_id}")
    print(f"Regen (raw)      : {regen_raw}  [{match_raw}]")
    print(f"Regen (normalised): {regen_norm}  [{match_norm}]")
    print()

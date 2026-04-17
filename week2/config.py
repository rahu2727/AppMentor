"""
week2/config.py — ChromaDB and embedding settings for AppMentor Week 2.

# ChromaDB and embedding settings only.
# Source paths, URLs, repo names, and module lists live in week2/config/.
# Edit the JSON files there — do not hardcode source config here.
"""

CONFIG: dict = {
    # ── ChromaDB ─────────────────────────────────────────────────────────────
    "chroma_persist_dir": "./week2/chroma_db",
    "collection_name":    "appmenter_erpnext",   # intentional spelling from spec
    "embedding_model":    "all-MiniLM-L6-v2",

    # ── Text chunking (character-based, used when splitting doc pages) ────────
    "chunking": {
        "chunk_size":    1200,
        "chunk_overlap":  200,
    },
}

"""
week2/config.py — Central settings for the AppMentor Week 2 knowledge base.

Import CONFIG anywhere in week2/ for consistent paths and parameters.
"""

CONFIG: dict = {
    # ── ChromaDB ─────────────────────────────────────────────────────────────
    "chroma_persist_dir": "./week2/chroma_db",
    "collection_name": "appmenter_erpnext",   # intentional spelling from spec
    "embedding_model": "all-MiniLM-L6-v2",

    # ── Text chunking ─────────────────────────────────────────────────────────
    "chunking": {
        "chunk_size": 1200,
        "chunk_overlap": 200,
    },

    # ── ERPNext documentation crawler ─────────────────────────────────────────
    # Short section names that map to docs.erpnext.com URL paths
    "docs": {
        "sections": [
            "hr",
            "accounts",
            "projects",
            "buying",
            "stock",
            "setting-up",
        ],
        "max_pages_per_section": 15,
    },

    # ── ERPNext source-code crawler ───────────────────────────────────────────
    "code": {
        "clone_dir": "./week2/data/erpnext_repo",
        "target_modules": [
            "erpnext/hr",
            "erpnext/accounts",
            "erpnext/payroll",
            "erpnext/projects",
            "erpnext/buying",
            "erpnext/stock",
        ],
    },
}

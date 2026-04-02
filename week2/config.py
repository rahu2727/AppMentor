"""
week2/config.py — Centralised settings for the Week 2 knowledge base.

Import this module anywhere in week2/ to get consistent paths and parameters.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Project root (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Week 2 directory
WEEK2_DIR = Path(__file__).parent.resolve()

# ChromaDB persistent storage (excluded from git via .gitignore)
CHROMA_DIR = PROJECT_ROOT / "chroma_db"

# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# ChromaDB collection
# ---------------------------------------------------------------------------

COLLECTION_NAME = "appmentor_kb"

# ---------------------------------------------------------------------------
# Retrieval defaults
# ---------------------------------------------------------------------------

# Number of results returned by query() unless caller overrides
DEFAULT_N_RESULTS = 5

# Cosine distance thresholds for colour-coded relevance in query_test.py
#   distance < GREEN_THRESHOLD  → green  (highly relevant)
#   distance < YELLOW_THRESHOLD → yellow (somewhat relevant)
#   distance >= YELLOW_THRESHOLD → red   (low relevance)
GREEN_THRESHOLD = 0.35
YELLOW_THRESHOLD = 0.60

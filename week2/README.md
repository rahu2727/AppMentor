# Week 2 — ERPNext Knowledge Base

**Goal:** Build a semantic knowledge base using ChromaDB + SentenceTransformers, seeded with 20 curated ERPNext Q&A pairs, queryable via cosine similarity search.

## What's here

| Path | Purpose |
|------|---------|
| `config.py` | All settings (paths, model name, thresholds) |
| `ingest.py` | CLI to ingest sources, reset, or view stats |
| `query_test.py` | Test runner with colour-coded relevance scores |
| `store/chroma_store.py` | ChromaDB wrapper (`add`, `query`, `stats`, `reset`) |
| `sources/forum_ingester.py` | 20 curated ERPNext Q&A seed pairs |

## Quick start

```bash
# From project root, with venv active:

# 1. Ingest the forum Q&A pairs
python week2/ingest.py --source forum

# 2. Check what's in the collection
python week2/ingest.py --stats

# 3. Run all 9 test queries
python week2/query_test.py

# 4. Ask your own question
python week2/query_test.py --query "How do I process payroll?"

# 5. Interactive mode
python week2/query_test.py --interactive

# 6. Wipe and start fresh
python week2/ingest.py --reset
```

## Architecture

```
ingest.py (CLI)
    │
    ├── sources/forum_ingester.py  → 20 Q&A pairs
    ├── sources/docs_ingester.py   → (stub, add in Week 3)
    └── sources/code_ingester.py   → (stub, add in Week 4)
            │
            ▼
    store/chroma_store.py
        ChromaDB PersistentClient  (disk: chroma_db/)
        + SentenceTransformer      (all-MiniLM-L6-v2)
            │
            ▼
    query_test.py  →  colour-coded cosine distance results
```

## Relevance colour coding

| Colour | Cosine distance | Meaning |
|--------|----------------|---------|
| GREEN  | < 0.35 | Highly relevant — good match |
| YELLOW | < 0.60 | Somewhat relevant — partial match |
| RED    | ≥ 0.60 | Low relevance — unrelated |

## Day-by-day plan (Days 6–9)

| Day | Task |
|-----|------|
| 6 | Set up ChromaDB, implement `chroma_store.py`, verify `add`/`query` |
| 7 | Implement `forum_ingester.py`, ingest 20 pairs, run `query_test.py` |
| 8 | Wire `ingest.py` CLI, test `--reset` / `--stats` flags |
| 9 | Tune thresholds, add 10 more Q&A pairs, prep for Week 3 integration |

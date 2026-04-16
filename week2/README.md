# Week 2 — ERPNext Knowledge Base

**Goal:** Build a local semantic knowledge base using ChromaDB +
SentenceTransformers, seeded with 20 curated ERPNext Q&A pairs, and
query it with cosine-similarity search.

---

## File map

| Path | Purpose |
|------|---------|
| `config.py` | Single `CONFIG` dict — all paths, model name, chunking settings |
| `ingest.py` | CLI to ingest sources, reset the DB, or view stats |
| `query_test.py` | Test runner — 9 queries with plain-text relevance labels |
| `store/chroma_store.py` | ChromaDB wrapper (`add`, `query`, `count`, `stats`, `reset`) |
| `sources/forum_ingester.py` | 20 curated ERPNext Q&A seed pairs |
| `sources/docs_ingester.py` | Crawls docs.erpnext.com (requires internet) |

---

## Quick start

Run all commands from the **project root** with your venv active.

```
# Step 1 — ingest the 20 built-in Q&A pairs (no internet required)
python week2/ingest.py --source forum

# Step 2 — check what is in the collection
python week2/ingest.py --stats

# Step 3 — run all 9 test queries
python week2/query_test.py

# Step 4 — ask your own question
python week2/query_test.py --query "How do I approve an expense?"

# Step 5 — interactive mode (Ctrl+C to quit)
python week2/query_test.py --interactive

# Step 6 — also crawl docs.erpnext.com (internet required, ~5 min)
python week2/ingest.py --source docs

# Step 7 — wipe the database and start fresh
python week2/ingest.py --reset
```

---

## Expected output: ingest

```
AppMentor — Week 2 Ingestion Pipeline
========================================

Ingesting source: forum
  [forum] 40 chunks added in 3.2s

Ingestion complete. Total chunks added this run: 40
Collection total: 40 chunks
```

_(40 chunks because each of the 20 Q&A pairs produces one question
chunk and one answer chunk.)_

---

## Expected output: query_test

```
Collection contains 40 chunk(s).

AppMentor Knowledge Base — Query Test Suite
Running 9 queries, top-3 results each
Relevance:  High (dist < 0.3)  Medium (dist < 0.5)  Low (dist >= 0.5)

Query: How do I submit an expense claim?
------------------------------------------------------------------------
  [1] Relevance: High    Distance: 0.051  Source: forum
       How do I submit an expense claim in ERPNext?
  [2] Relevance: High    Distance: 0.085  Source: forum
       Go to HR > Expenses > Expense Claim > New. Select the Employee...
  [3] Relevance: Medium  Distance: 0.312  Source: forum
       After submission the expense claim status changes to Submitted...

...

Summary: 9/9 queries scored High or Medium relevance
```

---

## Relevance thresholds

| Label  | Cosine distance | Meaning |
|--------|----------------|---------|
| High   | < 0.30 | Very close match — good answer |
| Medium | < 0.50 | Partial match — useful context |
| Low    | >= 0.50 | Weak match — unrelated content |

_(Cosine distance: 0 = identical vectors, 2 = opposite vectors.)_

---

## Common errors on Windows and how to fix them

### 1. `ModuleNotFoundError: No module named 'chromadb'`

Your virtual environment is not activated, or the packages are not
installed.

```
# Activate venv (Windows)
.\venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

---

### 2. `python` is not recognised

Python is not on your PATH. Use `py` instead:

```
py week2/ingest.py --source forum
py week2/query_test.py
```

Or add Python to your system PATH in Settings > System > Environment
Variables.

---

### 3. ChromaDB sqlite error — `no such module: fts5`

Python 3.12+ on Windows ships without the full SQLite build. Fix:

```
pip install pysqlite3-binary
```

Then add this at the very top of `ingest.py` and `query_test.py`:

```python
import pysqlite3
import sys
sys.modules["sqlite3"] = pysqlite3
```

---

### 4. `OSError: [Errno 22]` or permission error on `./week2/chroma_db`

Run your terminal as a normal user (not Administrator). Also make sure
no other process has the ChromaDB files open (e.g., a previous crashed
Python process).

---

### 5. Sentence-transformer model download hangs

The first run downloads `all-MiniLM-L6-v2` (~90 MB) from
Hugging Face. On a slow or firewalled connection this can time out.
Download it once with:

```
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

The model is cached in `%USERPROFILE%\.cache\huggingface\` and reused
on all subsequent runs.

---

### 6. Forum ingest runs but query_test shows only Low relevance

The chroma_db directory may contain an old collection with a different
embedding function. Wipe it and re-ingest:

```
python week2/ingest.py --reset
python week2/ingest.py --source forum
python week2/query_test.py
```

---

## Architecture

```
ingest.py (CLI)
    │
    ├─ sources/forum_ingester.py   20 built-in Q&A pairs
    ├─ sources/docs_ingester.py    crawls docs.erpnext.com
    └─ sources/code_ingester.py    (Week 3 — not yet built)
            │
            ▼
    store/chroma_store.py
        chromadb.PersistentClient  → disk: week2/chroma_db/
        SentenceTransformer        → all-MiniLM-L6-v2 (local)
            │
            ▼
    query_test.py  →  plain-text relevance labels + distances
```

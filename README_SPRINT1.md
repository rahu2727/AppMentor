# AppMentor — Sprint 1 Deployment Guide

AppMentor is a role-aware AI knowledge assistant for ERPNext. It retrieves answers
from a curated knowledge base (ChromaDB) and generates responses via the Anthropic API,
tailored to four user roles.

---

## What is built

| Component | Description |
|-----------|-------------|
| `week1/agent.py` | ReAct agent loop with web search and file tools |
| `week2/` | Knowledge base ingestion pipeline (ChromaDB + SentenceTransformer) |
| `app.py` | Streamlit chat UI — Sprint 1 deployment |

The knowledge base contains **~2,100+ chunks** from three sources:
- **Forum** — 40 curated ERPNext Q&A pairs
- **Docs** — 34 pages scraped from docs.frappe.io
- **Code** — ERPNext Python source and DocType JSON definitions

---

## Prerequisites

- Python 3.10+
- An `ANTHROPIC_API_KEY` in your `.env` file
- Knowledge base already ingested (see below)

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements_app.txt
```

### 2. Set up your API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Build the knowledge base (first time only)

```bash
python week2/ingest.py --source forum
python week2/ingest.py --source docs
python week2/ingest.py --source code
```

Or run all sources at once:

```bash
python week2/ingest.py
```

### 4. Launch the app

```bash
streamlit run app.py
```

Open your browser at **http://localhost:8501**

---

## Demo Questions

Try these questions after selecting a role in the sidebar:

1. **How do I submit an expense claim?**
   - As *End User*: step-by-step numbered guide
   - As *Developer*: DocType fields, controller logic, Python methods

2. **What is the approval workflow for leave applications?**
   - As *Manager*: policy overview, approval limits, team impact
   - As *Business User*: process steps and business rules

3. **How does payroll processing work in ERPNext?**
   - As *Developer*: Salary Slip DocType, payroll entry controller code

---

## Role Guide

| Role | Best for |
|------|----------|
| End User | Step-by-step guidance for daily tasks |
| Business User | Process flows, approval rules, policies |
| Manager | High-level overviews and team implications |
| Developer | DocType internals, Python code, field names |

---

## Sprint 2 Preview

Sprint 2 will add:
- Full ReAct agent loop integrated into the UI (live web search fallback)
- Conversation memory across turns
- Source document previews with highlighted matching text
- Multi-session support

---

## Project Structure

```
AppMentor/
├── app.py                   # Streamlit application (Sprint 1)
├── requirements_app.txt     # App dependencies
├── .streamlit/
│   └── config.toml          # Theme and server settings
├── .env                     # API keys (not committed)
├── week1/
│   ├── agent.py             # ReAct agent loop
│   └── tools.py             # web_search, read_text_file
└── week2/
    ├── config.py            # Central configuration
    ├── ingest.py            # Ingestion CLI
    ├── query_test.py        # Knowledge base test queries
    ├── chroma_db/           # Persisted vector store
    ├── store/
    │   └── chroma_store.py  # ChromaDB wrapper
    └── sources/
        ├── forum_ingester.py
        ├── docs_ingester.py
        └── code_ingester.py
```

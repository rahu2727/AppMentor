# AppMentor

An AI agents project built with LangGraph, ChromaDB, and the Anthropic API, targeting ERPNext as the demo application.

## Sprint Overview

| Week | Days | Focus |
|------|------|-------|
| Week 1 | Days 1–5 | ReAct agent with Anthropic tool use + Tavily search |
| Week 2 | Days 6–9 | ERPNext knowledge base with ChromaDB |
| Weeks 3–6 | Days 10+ | LangGraph orchestration, MCP server, Streamlit UI, demo polish |

## Quick Start

```bash
# 1. Clone and set up environment
git clone https://github.com/rahu2727/appmentor.git
cd appmentor
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY and TAVILY_API_KEY

# 3. Run the Week 1 ReAct agent
python week1/agent.py
# or ask a direct question:
python week1/agent.py "What is an ERPNext Item Group?"

# 4. Ingest the Week 2 knowledge base and test it
python week2/ingest.py --source forum
python week2/query_test.py
```

## Project Structure

```
appmenter/
├── .env.example          ← copy to .env and fill in your keys
├── requirements.txt      ← all Python dependencies
├── week1/                ← ReAct agent (Anthropic SDK + Tavily)
│   ├── agent.py
│   └── tools.py
├── week2/                ← ERPNext knowledge base (ChromaDB)
│   ├── ingest.py
│   ├── query_test.py
│   ├── config.py
│   ├── store/
│   │   └── chroma_store.py
│   └── sources/
│       └── forum_ingester.py
├── week3/                ← LangGraph multi-agent orchestration (coming soon)
├── week4/                ← MCP server integration (coming soon)
├── week5/                ← Streamlit UI (coming soon)
└── week6/                ← Demo polish and deployment (coming soon)
```

## Prerequisites

- Python 3.10+
- [Anthropic API key](https://console.anthropic.com/)
- [Tavily API key](https://tavily.com/) (free tier available)

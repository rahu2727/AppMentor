# Week 3 — LangGraph Multi-Agent Orchestration

**Status:** Coming soon (planned for Days 11–14)

## Goal

Wrap the Week 1 ReAct agent and Week 2 knowledge base into a LangGraph state machine with multiple specialised agents:

- **Router agent** — classifies the incoming question and routes to the right specialist
- **KB agent** — answers from the ChromaDB knowledge base (Week 2)
- **Search agent** — falls back to live web search via Tavily (Week 1 tools)
- **Summariser** — merges answers from multiple agents into a coherent response

## Planned files

```
week3/
├── graph.py          ← LangGraph StateGraph definition
├── nodes.py          ← individual node functions (router, kb, search, summarise)
├── state.py          ← TypedDict for shared graph state
└── README.md
```

## Running (once implemented)

```bash
python week3/graph.py "How do I set up payroll in ERPNext?"
```

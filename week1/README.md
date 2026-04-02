# Week 1 — ReAct Agent

**Goal:** Build a working ReAct (Reason + Act) agent using the Anthropic Python SDK with tool use.

## What's here

| File | Purpose |
|------|---------|
| `agent.py` | Full ReAct loop — Thought → Tool call → Observation → Answer |
| `tools.py` | `web_search` (Tavily) + `read_text_file`, plus Anthropic schema definitions |

## Quick start

```bash
# From the project root, with venv active:
python week1/agent.py                             # interactive REPL
python week1/agent.py "How do I create a PO in ERPNext?"
```

## How it works

```
User question
     │
     ▼
┌─────────────────────────────────────────────┐
│  Anthropic claude-sonnet-4-6                │
│  + SYSTEM prompt (ERPNext expert persona)   │
│  + TOOLS schema (web_search, read_text_file)│
└──────────────┬──────────────────────────────┘
               │ stop_reason = "tool_use"
               ▼
        Execute tool(s)
        (Tavily search / file read)
               │
               ▼
        Append tool_result to messages
               │
               └──► repeat (max 10 iterations)
                          │
                    stop_reason = "end_turn"
                          │
                          ▼
                    Final text answer
```

## Environment variables required

```
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...
```

Copy `.env.example` → `.env` and fill in your keys.

## Day-by-day plan (Days 1–5)

| Day | Task |
|-----|------|
| 1 | Set up venv, install deps, verify API keys work |
| 2 | Implement `tools.py` — test `web_search` in isolation |
| 3 | Implement `agent.py` — verify full ReAct loop |
| 4 | Tune system prompt, test with 10 ERPNext questions |
| 5 | Edge-case hardening, add iteration counter logging |

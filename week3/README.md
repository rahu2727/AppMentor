# Week 3 — LangGraph Agentic Pipeline

**Goal:** Upgrade appMentor from a RAG pipeline to a genuinely agentic system using LangGraph — with role-aware retrieval, a ReAct tool-selection loop, self-reflective quality scoring, and persona-based answer delivery.

## Architecture

```
START
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  DETECTIVE  (no API call — pure ChromaDB vector search)     │
│  • Picks chunk_type based on user_role + question keywords  │
│  • developer/admin   → raw_code priority                    │
│  • business/manager  → commentary priority                  │
│  • impact questions  → call_graph priority                  │
│  • Scores confidence = 1 − avg_cosine_distance              │
│  • Sets needs_reretrieval flag if confidence < 0.6          │
└──────────────────────┬──────────────────────────────────────┘
                       │ (conditional edge — always tracker,
                       │  tracker reads the flag)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  TRACKER  (ReAct loop — Anthropic tool_use)                 │
│  • If confidence < 0.6: asks Anthropic which tool to call   │
│  • Tools: search_commentary | search_raw_code |             │
│           search_call_graph | search_docs | search_forum    │
│  • Executes chosen tool → merges new chunks → re-scores     │
│  • Repeats up to 3 iterations                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  COUNSEL  (answer generation + self-reflection)             │
│  • Generates grounded answer from retrieved chunks          │
│  • Self-evaluates: grounded (1-5) + complete (1-5) +        │
│    role_appropriate (1-5) → quality_score avg               │
│  • If quality < 3.0 AND first attempt: graph retries once   │
└──────────────────────┬──────────────────────────────────────┘
                       │ (conditional edge)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  BRIEFER  (persona delivery)                                │
│  • Loads persona prompt from week2/prompts/<role>.txt       │
│  • Reformats raw_answer for tone/structure/depth of role    │
│  • Returns final_answer                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                      END
```

## Files

| File | Purpose |
|------|---------|
| `state.py` | `AppMentorState` TypedDict — all 16 fields |
| `graph.py` | LangGraph `StateGraph` wiring all 4 agents |
| `tools.py` | 5 Anthropic tool definitions + `execute_tool()` dispatcher |
| `pipeline.py` | `run(question, role) → dict` public interface |
| `test_pipeline.py` | Role comparison test + optional full suite |
| `agents/detective.py` | Role-aware ChromaDB retrieval + confidence scoring |
| `agents/tracker.py` | ReAct loop: assess → pick tool → retrieve → repeat |
| `agents/counsel.py` | Answer generation + self-reflection quality scoring |
| `agents/briefer.py` | Persona-aware answer formatting |

## Quick start

```bash
# Make sure the knowledge base is populated first
python week2/ingest.py --source forum

# Run the focused Developer vs Business User comparison (2 API calls)
python week3/test_pipeline.py --quick

# Ask a single question as a specific role
python week3/test_pipeline.py --role developer --q "How does the payroll submission work?"

# Run the full suite (15 API calls — takes ~2 min)
python week3/test_pipeline.py --full

# Use programmatically
python -c "
from week3.pipeline import run
result = run('How do I create a Purchase Order?', role='business_user')
print(result['answer'])
print('Confidence:', result['confidence'])
print('Tools used:', result['tools_used'])
"
```

## Role personas

Persona prompts live in `week2/prompts/`:

| Role | File | Tone |
|------|------|------|
| `developer` | `developer.txt` | Technical depth, code references, hooks |
| `business_user` | `business_user.txt` | Plain language, numbered steps, menu paths |
| `manager` | `manager.txt` | Outcomes, bullet points, <200 words |
| `system_admin` | `system_admin.txt` | Config, permissions, bench commands |
| `consultant` | `consultant.txt` | Best practices, tradeoffs, client framing |

## State fields

```python
AppMentorState = {
    # Inputs
    "user_question": str,
    "user_role":     str,

    # Retrieval
    "retrieved_chunks":     list[dict],   # {text, metadata, distance}
    "retrieval_confidence": float,        # 0.0 – 1.0
    "needs_reretrieval":    bool,
    "reformulated_query":   str,

    # Generation
    "raw_answer":       str,
    "quality_score":    float,            # avg of grounded+complete+role_appropriate
    "counsel_retries":  int,

    # Delivery
    "final_answer": str,

    # Provenance
    "sources":          list[str],
    "tool_calls_made":  list[str],
    "iteration_count":  int,
    "tracker_retries":  int,
    "messages":         list[dict],
}
```

## Day-by-day plan (Days 11–14)

| Day | Task |
|-----|------|
| 11 | Create state.py, tools.py, detective.py — verify ChromaDB queries |
| 12 | Implement tracker.py — test ReAct tool selection loop |
| 13 | Implement counsel.py + briefer.py — verify self-reflection scores |
| 14 | Wire graph.py + pipeline.py, run test_pipeline.py, tune thresholds |

# Week 6 — Polish and Demo

**Status:** Coming soon (planned for Days 23–26)

## Goal

End-to-end integration, demo recording, and deployment prep.

## Checklist

- [ ] Full pipeline smoke test: question → LangGraph → KB + Search → Streamlit UI
- [ ] Ingest full ERPNext documentation (crawl docs.erpnext.com)
- [ ] Ingest ERPNext GitHub source code (docstrings and comments)
- [ ] Performance tuning: embedding cache, async Tavily calls
- [ ] Demo script: 5 showcase questions with impressive answers
- [ ] Docker Compose for one-command local deployment
- [ ] README updated with architecture diagram and GIF demo

## Planned files

```
week6/
├── demo_script.py    ← runs the 5 showcase questions and records output
├── Dockerfile
├── docker-compose.yml
└── README.md
```

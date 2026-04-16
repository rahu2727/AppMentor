"""
app.py — AppMentor Sprint 1 Streamlit application.

Combines the Week 2 ChromaDB knowledge base with a role-aware
Anthropic call to answer ERPNext questions grounded in real content.

Run:
    streamlit run app.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Path setup — must happen before any local imports
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(_ROOT / "week2"))   # config, store.*
sys.path.insert(0, str(_ROOT / "week1"))   # agent, tools

import anthropic
import streamlit as st

from agent import run_agent          # week1/agent.py  (ReAct loop, Sprint 2+)
from config import CONFIG            # week2/config.py
from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AppMentor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------

ROLE_LABELS: dict[str, str] = {
    "end_user":      "End User — step by step guidance",
    "business_user": "Business User — process and policy",
    "manager":       "Manager — overview and architecture",
    "developer":     "Developer — technical detail and code",
}

ROLE_PROMPTS: dict[str, str] = {
    "end_user": (
        "You are AppMentor helping a new employee. "
        "Use simple language. Give numbered steps. "
        "Avoid technical jargon. End with who to contact if stuck."
    ),
    "business_user": (
        "You are AppMentor helping a business user. "
        "Focus on business rules, process steps, and policies. "
        "Reference approval workflows and business outcomes."
    ),
    "manager": (
        "You are AppMentor briefing a manager. "
        "Give high level overview first then key details. "
        "Focus on approval rules, limits, and team implications."
    ),
    "developer": (
        "You are AppMentor helping a developer. "
        "Include technical details: DocType names, field names, "
        "controller logic, Python methods where relevant. "
        "Reference the actual code and configurations."
    ),
}

# ---------------------------------------------------------------------------
# ChromaStore — cached so the embedding model loads exactly once
# ---------------------------------------------------------------------------


@st.cache_resource
def get_store() -> ChromaStore:
    return ChromaStore(
        persist_dir=CONFIG["chroma_persist_dir"],
        collection_name=CONFIG["collection_name"],
        embedding_model=CONFIG["embedding_model"],
    )


# ---------------------------------------------------------------------------
# Agent function — RAG + role-aware Anthropic call
# ---------------------------------------------------------------------------


def run_agent_with_kb(question: str, role: str) -> dict:
    """
    Query the knowledge base for context, then call the Anthropic API
    with a role-aware system prompt.

    Returns
    -------
    dict
        {"answer": str, "sources": list[str]}
    """
    try:
        store = get_store()
        results = store.query(query_text=question, n_results=5)

        # Build readable context from retrieved chunks
        context_parts: list[str] = []
        for r in results:
            meta  = r["metadata"]
            label = (
                meta.get("page_title")
                or meta.get("file_path")
                or meta.get("category")
                or meta.get("source", "knowledge base")
            )
            context_parts.append(f"[{label}]\n{r['text']}")
        context = "\n\n---\n\n".join(context_parts)

        system_prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS["end_user"])

        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Context from knowledge base:\n{context}"
                        f"\n\nQuestion: {question}"
                    ),
                }
            ],
        )

        sources = [
            r["metadata"].get("url")
            or r["metadata"].get("category")
            or r["metadata"].get("file_path", "ERPNext docs")
            for r in results
        ]

        return {"answer": response.content[0].text, "sources": sources}

    except Exception as exc:
        return {
            "answer": (
                "AppMentor encountered an error. "
                "Please check your API key and try again."
            ),
            "sources": [],
        }


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("AppMentor")
    st.caption("Your AI knowledge assistant for enterprise applications")

    st.divider()

    role: str = st.selectbox(
        "Select your role",
        options=list(ROLE_LABELS.keys()),
        format_func=lambda k: ROLE_LABELS[k],
    )

    st.divider()

    st.subheader("About")
    st.caption(
        "AppMentor reads your actual codebase and documentation. "
        "Answers are grounded in real content, not guesswork."
    )

    # Knowledge base stats
    try:
        _store = get_store()
        _count = _store.count()
        st.info(f"Knowledge base: {_count:,} chunks loaded")
    except Exception:
        st.warning("Knowledge base not loaded")

    st.divider()

    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.caption("Sprint 1 — ERPNext Knowledge Base")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.header("AppMentor")
st.caption(f"Answering as: {ROLE_LABELS[role]}")

# Welcome message shown only when chat is empty
if not st.session_state.messages:
    st.info(
        f"Ask me anything about ERPNext.  \n"
        f"I will answer based on your role as **{ROLE_LABELS[role]}**.  \n"
        f"Try: *How do I submit an expense claim?*"
    )

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            sources = [s for s in msg.get("sources", []) if s]
            if sources:
                with st.expander(f"Sources ({len(sources)})"):
                    for s in sources:
                        st.write(s)

# Chat input
if prompt := st.chat_input("Ask about ERPNext..."):

    # Add and display user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate and display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Investigating..."):
            result = run_agent_with_kb(prompt, role)

        st.markdown(result["answer"])

        sources = [s for s in result["sources"] if s]
        if sources:
            with st.expander(f"Sources ({len(sources)})"):
                for s in sources:
                    st.write(s)

    # Persist assistant message in session state
    st.session_state.messages.append(
        {
            "role":    "assistant",
            "content": result["answer"],
            "sources": result["sources"],
        }
    )

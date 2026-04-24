"""
week3/pipeline.py — Simple public interface for the appMentor agentic pipeline.

Usage:
    from week3.pipeline import run

    result = run("How do I run payroll?", role="business_user")
    print(result["answer"])
    print(result["confidence"])
    print(result["tools_used"])
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from week3.graph import get_graph
from week3.state import AppMentorState

VALID_ROLES = {"developer", "business_user", "manager", "system_admin", "consultant"}


def run(question: str, role: str = "business_user") -> dict:
    """
    Run the full appMentor agentic pipeline for a question and role.

    Args:
        question: Natural-language question about ERPNext.
        role:     One of developer | business_user | manager | system_admin | consultant.
                  Defaults to business_user.

    Returns a dict with:
        answer         — final persona-formatted answer (str)
        sources        — list of source tags used (list[str])
        confidence     — retrieval confidence score 0.0–1.0 (float)
        tools_used     — list of tool call log strings (list[str])
        iteration_count — total reasoning steps (int)
        quality_score  — self-reflection quality score 1.0–5.0 (float)
    """
    role_clean = role.lower().replace(" ", "_")
    if role_clean not in VALID_ROLES:
        role_clean = "business_user"

    initial_state: AppMentorState = {
        "user_question": question,
        "user_role": role_clean,
        "retrieved_chunks": [],
        "retrieval_confidence": 0.0,
        "needs_reretrieval": False,
        "reformulated_query": question,
        "raw_answer": "",
        "final_answer": "",
        "quality_score": 0.0,
        "counsel_retries": 0,
        "sources": [],
        "tool_calls_made": [],
        "iteration_count": 0,
        "tracker_retries": 0,
        "messages": [],
    }

    graph = get_graph()

    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        return {
            "answer": f"Pipeline error: {exc}",
            "sources": [],
            "confidence": 0.0,
            "tools_used": [],
            "iteration_count": 0,
            "quality_score": 0.0,
        }

    answer = final_state.get("final_answer") or final_state.get("raw_answer", "")
    if not answer:
        answer = "No answer could be generated. Check API keys and ChromaDB population."

    return {
        "answer": answer,
        "sources": final_state.get("sources", []),
        "confidence": round(final_state.get("retrieval_confidence", 0.0), 3),
        "tools_used": final_state.get("tool_calls_made", []),
        "iteration_count": final_state.get("iteration_count", 0),
        "quality_score": round(final_state.get("quality_score", 0.0), 2),
    }

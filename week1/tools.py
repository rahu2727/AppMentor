"""
week1/tools.py — Tool definitions for the AppMentor ReAct agent.

Implements:
  - web_search()      using TavilyClient (max 3 results)
  - read_text_file()  reads a local text / Python file

Also exports:
  - TOOLS     list of Anthropic function-calling schema dicts
  - TOOL_MAP  dict mapping tool name -> callable
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def web_search(query: str) -> str:
    """Search the web using Tavily and return a formatted string of results."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY not set in environment."

    client = TavilyClient(api_key=api_key)
    try:
        response = client.search(query=query, max_results=3)
    except Exception as exc:
        return f"Search failed: {exc}"

    results = response.get("results", [])
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r.get('title', 'No title')}")
        lines.append(f"    URL: {r.get('url', '')}")
        lines.append(f"    {r.get('content', '')[:400]}")
        lines.append("")

    return "\n".join(lines).strip()


def read_text_file(filepath: str) -> str:
    """Read a local text or Python file and return its contents."""
    path = Path(filepath)
    if not path.exists():
        return f"Error: file not found: {filepath}"
    if not path.is_file():
        return f"Error: path is not a file: {filepath}"

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading file: {exc}"

    max_chars = 8_000
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars ...]"
    return text


# ---------------------------------------------------------------------------
# Anthropic function-calling schema
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "web_search",
        "description": (
            "Search the web for up-to-date information. "
            "Use this when you need current facts, ERPNext documentation, "
            "forum answers, SAP notes, or anything not in your training data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_text_file",
        "description": (
            "Read the contents of a local text or Python file. "
            "Use this to inspect configuration files, logs, ABAP code, "
            "or any plain-text document the user points you at."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read.",
                },
            },
            "required": ["filepath"],
        },
    },
]

# Map tool name -> Python callable
TOOL_MAP: dict[str, callable] = {
    "web_search": web_search,
    "read_text_file": read_text_file,
}

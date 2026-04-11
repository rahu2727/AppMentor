"""
week1/agent.py — ReAct agent using the Anthropic Python SDK.

Usage:
    python week1/agent.py                          # interactive REPL
    python week1/agent.py "What is ERPNext?"       # single question via CLI

The agent follows the ReAct loop:
    Thought → Action (tool call) → Observation → ... → Final Answer

Safety guard: MAX_ITERATIONS = 10
Model: claude-sonnet-4-6
"""

import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# Add project root to path so sibling imports work from any cwd
sys.path.insert(0, str(Path(__file__).parent))
from tools import TOOL_MAP, TOOLS

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 10
SYSTEM_PROMPT = """You are AppMentor, an expert AI assistant specialising in ERPNext — \
the open-source ERP built on the Frappe framework.

You have access to two tools:
  • web_search      — search the web for up-to-date ERPNext docs, forum answers, and guides
  • read_text_file  — read a local file the user points you at

Think step-by-step. When you need information, call a tool. \
When you have enough information to answer, reply directly without calling any more tools.

Be concise but thorough. Cite sources (URLs) when you use web_search results."""

# ---------------------------------------------------------------------------
# Core ReAct loop
# ---------------------------------------------------------------------------


def run_agent(question: str, verbose: bool = True) -> str:
    """
    Run the ReAct loop for a single question and return the final answer.

    Args:
        question: The user's question.
        verbose:  If True, print intermediate steps to stdout.

    Returns:
        The agent's final text answer.
    """
    client = anthropic.Anthropic()

    messages: list[dict] = [{"role": "user", "content": question}]

    for iteration in range(1, MAX_ITERATIONS + 1):
        if verbose:
            print(f"\n{'─' * 60}")
            print(f"  Iteration {iteration}/{MAX_ITERATIONS}")
            print(f"{'─' * 60}")

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant turn to history
        messages.append({"role": "assistant", "content": response.content})

        if verbose:
            print(f"  Stop reason: {response.stop_reason}")

        # ── Final answer: no more tool calls ────────────────────────────────
        if response.stop_reason == "end_turn":
            final_text = _extract_text(response.content)
            return final_text

        # ── Tool use ─────────────────────────────────────────────────────────
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                if verbose:
                    print(f"\n  Tool call: {tool_name}")
                    print(f"  Input:     {json.dumps(tool_input, indent=2)}")

                fn = TOOL_MAP.get(tool_name)
                if fn is None:
                    result_text = f"Error: unknown tool '{tool_name}'"
                else:
                    try:
                        result_text = fn(**tool_input)
                    except Exception as exc:
                        result_text = f"Tool error: {exc}"

                if verbose:
                    preview = result_text[:300].replace("\n", " ")
                    print(f"  Result:    {preview}{'…' if len(result_text) > 300 else ''}")

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )

            # Feed observations back into the conversation
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — treat remaining text as final answer
        return _extract_text(response.content)

    return (
        "I reached the maximum number of reasoning steps without a conclusive answer. "
        "Please try rephrasing your question or breaking it into smaller parts."
    )


def _extract_text(content: list) -> str:
    """Pull plain text out of an Anthropic response content list."""
    parts = []
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def interactive_mode() -> None:
    """Simple REPL for multi-turn questions (each question is independent)."""
    print("AppMentor ReAct Agent — type 'exit' or 'quit' to stop.\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        answer = run_agent(question, verbose=True)
        print(f"\nAppMentor: {answer}\n")


def main() -> None:
    if len(sys.argv) > 1:
        # Single question mode
        question = " ".join(sys.argv[1:])
        print(f"Question: {question}\n")
        answer = run_agent(question, verbose=True)
        print(f"\nFinal Answer:\n{answer}")
    else:
        interactive_mode()


if __name__ == "__main__":
    main()

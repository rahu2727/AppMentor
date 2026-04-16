"""
week1/agent.py — ReAct agent using the Anthropic Python SDK.

Usage:
    python week1/agent.py                                # interactive REPL
    python week1/agent.py "What is ERPNext?"             # single question
    python week1/agent.py                                # press Enter to run TEST_QUESTIONS

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

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).parent))
from tools import TOOL_MAP, TOOLS

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 10

SYSTEM_PROMPT = (
    "You are AppMentor, an expert AI assistant for enterprise applications. "
    "Answer questions about ERPNext, SAP Z-code, and custom applications. "
    "Always cite sources. "
    "Use tools to find accurate information before answering."
)

TEST_QUESTIONS = [
    "How do I submit an expense claim in ERPNext?",
    "What happens if my leave approver is also on leave?",
    "What is the difference between a Purchase Order and a Material Request in ERPNext?",
]

# ---------------------------------------------------------------------------
# Core ReAct loop
# ---------------------------------------------------------------------------


def run_agent(question: str, verbose: bool = True) -> str:
    """
    Run the ReAct loop for a single question and return the final answer.

    Args:
        question: The user's question.
        verbose:  If True, prints [Tool] lines and iteration headers.

    Returns:
        The agent's final text answer as a plain string.
    """
    client = anthropic.Anthropic()

    messages: list[dict] = [{"role": "user", "content": question}]

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant turn to conversation history
        messages.append({"role": "assistant", "content": response.content})

        # ── Final answer ─────────────────────────────────────────────────────
        if response.stop_reason == "end_turn":
            return _extract_text(response.content)

        # ── Tool calls ───────────────────────────────────────────────────────
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                if verbose:
                    # Compact single-line representation of the input
                    input_repr = json.dumps(tool_input, ensure_ascii=False)
                    print(f"[Tool] {tool_name}({input_repr})")

                fn = TOOL_MAP.get(tool_name)
                if fn is None:
                    result_text = f"Error: unknown tool '{tool_name}'"
                else:
                    try:
                        result_text = fn(**tool_input)
                    except Exception as exc:
                        result_text = f"Tool error: {exc}"

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )

            # Feed tool observations back into the conversation
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — return whatever text is present
        return _extract_text(response.content)

    return (
        "I reached the maximum number of reasoning steps without a conclusive answer. "
        "Please try rephrasing your question or breaking it into smaller parts."
    )


def _extract_text(content: list) -> str:
    """Pull plain text blocks out of an Anthropic response content list."""
    parts = []
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("AppMentor — Week 1 ReAct Agent")
    print("=" * 40)

    if len(sys.argv) > 1:
        # Single question passed on the command line
        question = " ".join(sys.argv[1:])
        print(f"\nQuestion: {question}\n")
        answer = run_agent(question, verbose=True)
        print(f"\nAnswer:\n{answer}\n")
    else:
        # Interactive mode
        print("Type your question and press Enter.")
        print("Press Enter with no question to run all test questions.")
        print("Type 'exit' or 'quit' to stop.\n")

        while True:
            try:
                question = input("Ask AppMentor: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if question.lower() in {"exit", "quit"}:
                print("Goodbye!")
                break

            if not question:
                # Run all three built-in test questions
                print("\nNo question entered — running all test questions.\n")
                for i, q in enumerate(TEST_QUESTIONS, 1):
                    print(f"\n{'=' * 60}")
                    print(f"Test {i}: {q}")
                    print("=" * 60)
                    answer = run_agent(q, verbose=True)
                    print(f"\nAnswer:\n{answer}\n")
                break

            answer = run_agent(question, verbose=True)
            print(f"\nAnswer:\n{answer}\n")

"""
week3/test_pipeline.py — Test runner for the appMentor LangGraph pipeline.

Runs a focused Developer vs Business User comparison on the same question,
then optionally runs the full 5-role × 3-question suite.

Usage:
    python week3/test_pipeline.py                # comparison + optional full suite
    python week3/test_pipeline.py --quick        # comparison only (2 API calls)
    python week3/test_pipeline.py --full         # always run full suite
    python week3/test_pipeline.py --role developer --q "How does payroll work?"
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── ANSI colours ─────────────────────────────────────────────────────────────
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
RESET  = "\033[0m"

# ── Test data ─────────────────────────────────────────────────────────────────
TEST_QUESTIONS = [
    "How do I run payroll for all employees at month end?",
    "What happens when a Purchase Order is submitted?",
    "How do I reconcile bank transactions in ERPNext?",
]

ALL_ROLES = ["developer", "business_user", "manager", "system_admin", "consultant"]

COMPARISON_QUESTION = TEST_QUESTIONS[0]
COMPARISON_ROLES    = ["developer", "business_user"]

# Technical terms that should appear more in developer answers
_TECH_TERMS = {
    "python", "doctype", "api", "method", "class", "function", "field",
    "frappe", "hook", "controller", "database", "sql", "script", "bench",
    "docfield", "server", "client", "whitelisted", "validate", "submit",
}


# ── Prerequisites check ───────────────────────────────────────────────────────

def check_prerequisites() -> bool:
    ok = True

    if not os.getenv("ANTHROPIC_API_KEY"):
        print(f"{YELLOW}WARNING: ANTHROPIC_API_KEY is not set. Agents will fail.{RESET}")
        print(f"{DIM}Copy .env.example → .env and add your key.{RESET}\n")
        ok = False

    try:
        from week2.store.chroma_store import ChromaStore
        store = ChromaStore()
        count = store.count()
        if count == 0:
            print(f"{YELLOW}WARNING: ChromaDB is empty.{RESET}")
            print(f"{DIM}Run first: python week2/ingest.py --source forum{RESET}")
            print(f"{DIM}Agents will still run but answers will have low confidence.{RESET}\n")
        else:
            print(f"{GREEN}ChromaDB: {count} document(s) ready.{RESET}")
    except Exception as exc:
        print(f"{YELLOW}WARNING: ChromaDB unavailable — {exc}{RESET}\n")

    return ok


# ── Display helpers ───────────────────────────────────────────────────────────

def _conf_colour(conf: float) -> str:
    if conf >= 0.6:
        return GREEN
    if conf >= 0.3:
        return YELLOW
    return RED


def print_result(role: str, result: dict) -> None:
    conf     = result["confidence"]
    iters    = result["iteration_count"]
    quality  = result["quality_score"]
    tools    = result["tools_used"]
    answer   = result["answer"]
    words    = len(answer.split())

    print(f"\n  {BOLD}Role:{RESET} {role}")
    print(
        f"  {BOLD}Confidence:{RESET} {_conf_colour(conf)}{conf:.3f}{RESET}  "
        f"{BOLD}Iterations:{RESET} {iters}  "
        f"{BOLD}Quality:{RESET} {quality:.1f}/5  "
        f"{BOLD}Words:{RESET} {words}"
    )
    if tools:
        print(f"  {BOLD}Tools called:{RESET}")
        for t in tools:
            print(f"    {DIM}{t}{RESET}")
    else:
        print(f"  {BOLD}Tools called:{RESET} {DIM}none{RESET}")

    preview = answer[:350].replace("\n", " ")
    ellipsis = "…" if len(answer) > 350 else ""
    print(f"  {BOLD}Answer preview:{RESET}\n  {DIM}{preview}{ellipsis}{RESET}")


# ── Comparison run ────────────────────────────────────────────────────────────

def run_comparison() -> None:
    from week3.pipeline import run

    print(f"\n{'='*72}")
    print(f"{BOLD}{CYAN}  ROLE COMPARISON: Developer vs Business User{RESET}")
    print(f"{'='*72}")
    print(f"  Question: {COMPARISON_QUESTION}\n")

    results: dict[str, dict | None] = {}

    for role in COMPARISON_ROLES:
        print(f"  Running {BOLD}{role}{RESET}...", end="", flush=True)
        try:
            results[role] = run(COMPARISON_QUESTION, role)
            conf = results[role]["confidence"]
            print(f" done  (confidence={conf:.2f})")
        except Exception as exc:
            print(f" {RED}ERROR: {exc}{RESET}")
            results[role] = None

    # Print individual results
    for role in COMPARISON_ROLES:
        if results[role]:
            print_result(role, results[role])

    # Analyse differences
    dev_result = results.get("developer")
    biz_result = results.get("business_user")

    if dev_result and biz_result:
        print(f"\n  {BOLD}Are the answers genuinely different?{RESET}")

        dev_terms = set(dev_result["answer"].lower().split()) & _TECH_TERMS
        biz_terms = set(biz_result["answer"].lower().split()) & _TECH_TERMS

        dev_only  = dev_terms - biz_terms
        biz_only  = biz_terms - dev_terms

        print(f"    Technical terms in developer answer only : {DIM}{', '.join(sorted(dev_only)) or 'none'}{RESET}")
        print(f"    Technical terms in business answer only  : {DIM}{', '.join(sorted(biz_only)) or 'none'}{RESET}")

        dev_words = len(dev_result["answer"].split())
        biz_words = len(biz_result["answer"].split())
        print(f"    Word count — developer: {dev_words}, business user: {biz_words}")

        if dev_only or dev_words != biz_words:
            print(f"    {GREEN}✓ Answers are genuinely different — persona formatting is working{RESET}")
        else:
            print(f"    {YELLOW}Answers are similar. Ingest more data for stronger role differentiation.{RESET}")


# ── Full suite ────────────────────────────────────────────────────────────────

def run_full_suite() -> None:
    from week3.pipeline import run

    print(f"\n{'='*72}")
    print(f"{BOLD}{CYAN}  FULL SUITE — {len(ALL_ROLES)} roles × {len(TEST_QUESTIONS)} questions{RESET}")
    print(f"{'='*72}")

    total_ok = 0
    total_err = 0

    for q_idx, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\n{BOLD}Q{q_idx}: {question}{RESET}")
        print("-" * 72)

        for role in ALL_ROLES:
            print(f"  {role:15s} ", end="", flush=True)
            try:
                result = run(question, role)
                conf   = result["confidence"]
                iters  = result["iteration_count"]
                words  = len(result["answer"].split())
                n_tools = len(result["tools_used"])
                col    = _conf_colour(conf)
                print(
                    f"conf={col}{conf:.2f}{RESET}  "
                    f"iters={iters}  words={words}  tools={n_tools}"
                )
                total_ok += 1
            except Exception as exc:
                print(f"{RED}ERROR: {exc}{RESET}")
                total_err += 1

    print(f"\n{BOLD}Suite complete:{RESET} {GREEN}{total_ok} passed{RESET}, {RED}{total_err} failed{RESET}")


# ── Single query mode ─────────────────────────────────────────────────────────

def run_single(question: str, role: str) -> None:
    from week3.pipeline import run

    print(f"\n{BOLD}Question:{RESET} {question}")
    print(f"{BOLD}Role:{RESET} {role}\n")
    print("Running...", end="", flush=True)
    try:
        result = run(question, role)
        print(" done\n")
        print_result(role, result)
        print(f"\n{BOLD}Full answer:{RESET}\n{result['answer']}")
    except Exception as exc:
        print(f"\n{RED}ERROR: {exc}{RESET}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="appMentor LangGraph pipeline test runner")
    p.add_argument("--quick", action="store_true", help="Run comparison only (2 API calls)")
    p.add_argument("--full",  action="store_true", help="Always run the full suite after comparison")
    p.add_argument("--role",  default=None,        help="Role for single-query mode")
    p.add_argument("--q",     default=None,        dest="question", help="Single question to run")
    return p


def main() -> None:
    args = build_parser().parse_args()

    print(f"\n{BOLD}appMentor — LangGraph Pipeline Test{RESET}")
    print(f"{'='*72}")

    check_prerequisites()

    # Single-query mode
    if args.question:
        role = args.role or "business_user"
        run_single(args.question, role)
        return

    # Comparison (always runs)
    run_comparison()

    # Full suite
    if args.full:
        run_full_suite()
    elif not args.quick:
        print(f"\n{DIM}Full suite = {len(ALL_ROLES) * len(TEST_QUESTIONS)} API calls. Run with --full to execute.{RESET}")

    print(f"\n{GREEN}Done.{RESET}\n")


if __name__ == "__main__":
    main()

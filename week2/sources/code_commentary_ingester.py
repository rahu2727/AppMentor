"""
week2/sources/code_commentary_ingester.py
Reads Python functions from the ERPNext codebase, generates plain-English
commentary via the Claude API, and stores both commentary and raw code in
ChromaDB.

Target modules (cost-controlled subset):
  erpnext/hr, erpnext/payroll, erpnext/buying, erpnext/projects

erpnext/stock and erpnext/accounts are intentionally excluded:
  stock contains 150+ files with complex valuation, ledger and perpetual
  inventory logic — too expensive and noisy to annotate for a demo.
  accounts has similar scale and depth.

Public API
----------
    from sources.code_commentary_ingester import run
    chunks_added = run(store, config, dry_run=False, max_functions=999)
"""

from __future__ import annotations

import ast
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
from dotenv import load_dotenv

from store.chroma_store import ChromaStore

load_dotenv()

# ---------------------------------------------------------------------------
# Target modules — cost-controlled subset
# ---------------------------------------------------------------------------

# erpnext/stock and erpnext/accounts are excluded (see module docstring).
_DEFAULT_MODULES: list[str] = [
    "erpnext/hr",
    "erpnext/payroll",
    "erpnext/buying",
    "erpnext/projects",
]

_ERPNEXT_REPO_URL = "https://github.com/frappe/erpnext.git"

# Cost estimate for claude-sonnet-4-6 (input $3/MTok, output $15/MTok).
# Average function: ~300 input tokens + ~200 output tokens ≈ $0.004 each.
_COST_PER_FUNCTION: float = 0.004

_MIN_FUNCTION_LINES: int = 5   # skip trivial one-liners and property wrappers
_API_DELAY: float = 0.5        # seconds between API calls (rate-limit buffer)


# ---------------------------------------------------------------------------
# Repo helpers
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    return shutil.which("git") is not None


def _clone_repo(clone_dir: Path) -> bool:
    if not _git_available():
        print(
            "  [ERROR] 'git' command not found.\n"
            "          Install Git then re-run."
        )
        return False

    print(f"  Cloning ERPNext repo (shallow) into {clone_dir} ...")
    print("  This may take 2-5 minutes depending on your connection.")
    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--single-branch",
                _ERPNEXT_REPO_URL,
                str(clone_dir),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            print(
                f"  [ERROR] git clone failed (exit {result.returncode}).\n"
                f"          {result.stderr.strip()}"
            )
            return False
        print("  Clone complete.")
        return True
    except subprocess.TimeoutExpired:
        print("  [ERROR] git clone timed out after 10 minutes.")
        return False
    except Exception as exc:
        print(f"  [ERROR] Unexpected error during clone: {exc}")
        return False


def _find_package_root(clone_dir: Path) -> Path:
    if (clone_dir / "erpnext" / "__init__.py").exists():
        return clone_dir
    for subdir in sorted(clone_dir.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("."):
            if (subdir / "erpnext" / "__init__.py").exists():
                return subdir
    return clone_dir


# ---------------------------------------------------------------------------
# AST function extraction
# ---------------------------------------------------------------------------


def _extract_functions(file_path: Path) -> list[tuple[str, str, int]]:
    """
    Parse one Python file and return (name, source_code, line_count) tuples
    for every qualifying FunctionDef node.

    Excluded:
    - Functions under _MIN_FUNCTION_LINES lines (too trivial)
    - Dunder methods  (__init__, __str__, etc.)
    - Test functions  (test_*)
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    results: list[tuple[str, str, int]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        name = node.name

        if name.startswith("__") and name.endswith("__"):
            continue
        if name.startswith("test_"):
            continue

        line_count = node.end_lineno - node.lineno + 1
        if line_count < _MIN_FUNCTION_LINES:
            continue

        source = ast.get_source_segment(content, node)
        if source is None:
            # Fallback for older Python builds
            lines = content.splitlines()
            source = "\n".join(lines[node.lineno - 1 : node.end_lineno])

        if not source or not source.strip():
            continue

        results.append((name, source.strip(), line_count))

    return results


# ---------------------------------------------------------------------------
# Chunk ID helpers
# ---------------------------------------------------------------------------


def _commentary_id(file_path: str, function_name: str) -> str:
    return hashlib.md5(
        f"commentary-{file_path}-{function_name}".encode("utf-8")
    ).hexdigest()


def _raw_code_id(file_path: str, function_name: str) -> str:
    return hashlib.md5(
        f"raw_code-{file_path}-{function_name}".encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a senior enterprise software developer "
    "reviewing Python code. Write a concise plain English "
    "explanation that a business analyst or new developer "
    "can understand. Focus on WHAT the function does and "
    "WHY, not HOW. Use business language where possible."
)


def _generate_commentary(
    client: anthropic.Anthropic,
    function_name: str,
    file_path: str,
    module_name: str,
    source_code: str,
) -> str | None:
    """Call Claude and return the commentary text, or None on failure."""
    user_message = (
        f"Function name: {function_name}\n"
        f"File: {file_path}\n"
        f"Module: {module_name}\n\n"
        f"Code:\n{source_code}\n\n"
        "Write a commentary covering:\n"
        "1. What this function does (one sentence)\n"
        "2. Business purpose — what business process does it serve\n"
        "3. Key inputs and what they represent in business terms\n"
        "4. What it returns or what change it makes\n"
        "5. Any important business rules or validations embedded\n"
        "6. Edge cases or error conditions handled\n\n"
        "Keep the total response under 150 words."
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except Exception as exc:
        print(f"    [API ERROR] {function_name}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    store: ChromaStore,
    config: dict,
    dry_run: bool = False,
    max_functions: int = 999,
) -> int:
    """
    Generate AI commentary for Python functions in the ERPNext codebase.

    Parameters
    ----------
    store : ChromaStore
        Destination knowledge base.
    config : dict
        CONFIG dict from week2/config.py.
    dry_run : bool
        If True, scan and report without calling the API or storing anything.
    max_functions : int
        Cap on functions to process (default 999). Set to 50 for testing.

    Returns
    -------
    int
        Total chunks added (0 in dry_run mode).
    """
    clone_dir_str: str = config.get("code", {}).get(
        "clone_dir", "./week2/data/erpnext_repo"
    )
    target_modules: list[str] = config.get("code_commentary", {}).get(
        "target_modules", _DEFAULT_MODULES
    )

    project_root = Path(__file__).parent.parent.parent
    clone_dir = (project_root / clone_dir_str).resolve()

    # ── Ensure repo is available ─────────────────────────────────────────────
    if not clone_dir.exists() or not any(clone_dir.iterdir()):
        print(f"  ERPNext repo not found at {clone_dir}")
        if dry_run:
            print(
                "  DRY RUN — would target modules:\n"
                + "\n".join(f"    {m}" for m in target_modules)
            )
            print("  Cannot count functions without the repo. Run:")
            print("    python week2/ingest.py --source code")
            return 0
        success = _clone_repo(clone_dir)
        if not success:
            print("  Hint: run `python week2/ingest.py --source code` first.")
            return 0

    package_root = _find_package_root(clone_dir)
    print(f"  Using repo at: {package_root}")

    if dry_run:
        print("  DRY RUN — no API calls will be made, nothing stored.\n")

    # ── Collect qualifying functions across all target modules ────────────────
    # List of (function_name, source_code, rel_file_path, module_name, line_count)
    all_functions: list[tuple[str, str, str, str, int]] = []

    for module_name in target_modules:
        module_dir = package_root / module_name
        if not module_dir.exists():
            print(f"  [WARN] Module not found: {module_dir} — skipping")
            continue

        py_files = list(module_dir.rglob("*.py"))
        module_count = 0

        for py_file in py_files:
            rel_path = str(py_file.relative_to(package_root))
            for fn_name, fn_source, fn_lines in _extract_functions(py_file):
                all_functions.append(
                    (fn_name, fn_source, rel_path, module_name, fn_lines)
                )
                module_count += 1

        print(f"  {module_name}: {module_count} qualifying functions found")

    total_found = len(all_functions)
    to_process = min(total_found, max_functions)

    print(f"\n  Total qualifying functions : {total_found}")
    print(f"  Will process              : {to_process}  (max_functions={max_functions})")

    if not dry_run:
        print(f"  Estimated cost            : ${to_process * _COST_PER_FUNCTION:.2f}")

    if dry_run:
        print("\n  DRY RUN complete — no changes made.")
        return 0

    # ── API calls and ChromaDB storage ───────────────────────────────────────
    client = anthropic.Anthropic()
    total_chunks_added = 0
    processed = 0
    cost_so_far = 0.0

    for fn_name, fn_source, rel_path, module_name, line_count in all_functions[:to_process]:

        commentary = _generate_commentary(
            client, fn_name, rel_path, module_name, fn_source
        )

        if commentary is None:
            time.sleep(_API_DELAY)
            continue

        # ── Commentary chunk ──────────────────────────────────────────────────
        commentary_text = (
            f"Function: {fn_name}\n"
            f"File: {rel_path}\n"
            f"Module: {module_name}\n\n"
            f"{commentary}"
        )
        added_c = store.add(
            texts=[commentary_text],
            metadatas=[{
                "source":              "code_commentary",
                "file_path":           rel_path,
                "function_name":       fn_name,
                "module":              module_name,
                "chunk_type":          "commentary",
                "generated_by":        "claude-sonnet-4-6",
                "original_code_lines": line_count,
            }],
            ids=[_commentary_id(rel_path, fn_name)],
        )
        total_chunks_added += added_c

        # ── Raw code chunk ────────────────────────────────────────────────────
        added_r = store.add(
            texts=[fn_source],
            metadatas=[{
                "source":              "code_commentary",
                "file_path":           rel_path,
                "function_name":       fn_name,
                "module":              module_name,
                "chunk_type":          "raw_code",
                "generated_by":        "claude-sonnet-4-6",
                "original_code_lines": line_count,
            }],
            ids=[_raw_code_id(rel_path, fn_name)],
        )
        total_chunks_added += added_r

        processed += 1
        cost_so_far = processed * _COST_PER_FUNCTION

        if processed % 10 == 0:
            print(
                f"  Processed {processed}/{to_process} functions"
                f" — estimated cost so far: ${cost_so_far:.2f}"
            )

        time.sleep(_API_DELAY)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  Commentary complete:")
    print(f"    Functions processed : {processed}")
    print(f"    Chunks added        : {total_chunks_added}")
    print(f"    Estimated cost      : ${cost_so_far:.2f}")

    return total_chunks_added

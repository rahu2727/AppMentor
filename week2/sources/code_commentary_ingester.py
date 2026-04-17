"""
week2/sources/code_commentary_ingester.py

# Configuration is externalised to week2/config/
# To change sources, URLs or paths edit the JSON files in that folder
# — do not hardcode values here

Reads Python functions from configured ERPNext/HRMS modules, generates
plain-English commentary via the Claude API, and stores both commentary
and raw code chunks in ChromaDB.

Repositories, module paths, model name, and API settings are all read
from sources_code.json via ConfigLoader — nothing is hardcoded here.

Public API
----------
    from sources.code_commentary_ingester import run
    chunks_added = run(store, config_loader, dry_run=False, max_functions=999)
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

# Cost estimate for claude-sonnet-4-6 (input $3/MTok, output $15/MTok).
# ~300 input tokens + ~200 output tokens per function ≈ $0.004 each.
# This is derived from API pricing; it is not a tuneable config value.
_COST_PER_FUNCTION: float = 0.004


# ---------------------------------------------------------------------------
# Repo clone helpers
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    return shutil.which("git") is not None


def _clone_repo(clone_dir: Path, url: str, label: str) -> bool:
    """Shallow-clone *url* into *clone_dir*. Returns True on success."""
    if not _git_available():
        print("  [ERROR] 'git' command not found. Install Git then re-run.")
        return False

    print(f"  Cloning {label} (shallow) into {clone_dir} ...")
    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--single-branch",
                "--config", "core.protectNTFS=false",
                url,
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
        print(f"  Clone complete: {label}")
        return True
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] git clone timed out ({label}).")
        return False
    except Exception as exc:
        print(f"  [ERROR] {exc}")
        return False


# ---------------------------------------------------------------------------
# Module path resolution
# ---------------------------------------------------------------------------


def _locate_module(repo_dir: Path, candidates: list[str], label: str) -> Path | None:
    """
    Try each candidate path inside *repo_dir* using os.path.isdir().
    Prints [OK] on match or [WARN] if nothing found.
    """
    for candidate in candidates:
        full_path = repo_dir / candidate
        if os.path.isdir(full_path):
            print(f"  [OK] Found {label} module at: {full_path}")
            return full_path
    print(f"  [WARN] Could not find {label} module in {repo_dir.name} — skipping")
    return None


# ---------------------------------------------------------------------------
# AST function extraction
# ---------------------------------------------------------------------------


def _extract_functions(
    file_path: Path,
    min_lines: int = 5,
) -> list[tuple[str, str, int]]:
    """
    Parse one .py file; return (name, source_code, line_count) for every
    qualifying FunctionDef.

    Excluded: under *min_lines* lines, dunder methods, test_ functions.
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
        if line_count < min_lines:
            continue

        source = ast.get_source_segment(content, node)
        if source is None:
            lines  = content.splitlines()
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
    "You are a senior enterprise software developer reviewing "
    "Python code. Write a concise plain English explanation "
    "that a business analyst or new developer can understand. "
    "Focus on WHAT the function does and WHY, not HOW. "
    "Use business language throughout. Never use programming "
    "terms like iterate, loop, return, or boolean. Replace "
    "them with business equivalents \u2014 for example say "
    "\"the system moves to the next stage\" not \"returns true\". "
    "Always state whether the function runs automatically "
    "or requires a user action."
)


def _generate_commentary(
    client: anthropic.Anthropic,
    function_name: str,
    file_path: str,
    module_label: str,
    source_code: str,
    model: str,
    max_tokens: int,
) -> str | None:
    """Call Claude and return commentary text, or None on failure."""
    user_message = (
        f"Function name: {function_name}\n"
        f"File: {file_path}\n"
        f"Module: {module_label}\n\n"
        f"Code:\n{source_code}\n\n"
        "Write a commentary covering:\n"
        "1. What this function does (one sentence)\n"
        "2. Business purpose \u2014 what business process does it serve\n"
        "3. Key inputs and what they represent in business terms\n"
        "4. What it changes or what action it triggers in the system\n"
        "5. Any important business rules or validations embedded\n"
        "6. Edge cases or error conditions handled\n"
        "7. Is this triggered automatically by the system or "
        "manually by a user? What event causes it to run?\n\n"
        "Keep the total response under 200 words.\n"
        "Complex functions with multiple business rules may use "
        "the full limit. Simple functions should be shorter."
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
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
    config_loader,
    dry_run: bool = False,
    max_functions: int = 999,
) -> int:
    """
    Generate AI commentary for Python functions from configured repos.

    Parameters
    ----------
    store : ChromaStore
        Destination knowledge base.
    config_loader : ConfigLoader
        Loaded configuration; supplies repos, module paths, and agent settings.
    dry_run : bool
        If True, scan and count without calling the API or storing anything.
    max_functions : int
        Cap on functions to process. Use 20 for a test run.

    Returns
    -------
    int
        Total chunks added (0 in dry_run mode).
    """
    project_root = Path(__file__).parent.parent.parent

    # ── Read settings from config ─────────────────────────────────────────────
    commentary   = config_loader.get_commentary_settings()
    model        = commentary.get("model",              "claude-sonnet-4-6")
    max_tokens   = commentary.get("max_tokens",         300)
    api_delay    = commentary.get("api_delay_seconds",  0.5)
    cost_warning = commentary.get("cost_warning_threshold_usd", 5.0)

    chunking   = config_loader.get_chunking_settings()
    min_lines  = chunking.get("min_function_lines",  5)

    if dry_run:
        print("  DRY RUN — no API calls will be made, nothing stored.\n")

    # ── Check / clone repos ──────────────────────────────────────────────────
    print("  Checking repositories ...")
    ready_repos: set[str] = set()

    for repo in config_loader.get_enabled_repos():
        clone_dir = (project_root / repo["local_path"]).resolve()
        label     = repo["name"]

        if clone_dir.exists() and any(clone_dir.iterdir()):
            print(f"  Repo already present: {clone_dir.name}")
            ready_repos.add(label)
        elif dry_run:
            print(f"  [DRY RUN] Repo not found: {clone_dir.name}")
        else:
            if _clone_repo(clone_dir, repo["clone_url"], label):
                ready_repos.add(label)

    print()

    # ── Collect qualifying functions across all target modules ────────────────
    # Tuple: (fn_name, fn_source, rel_path, module_label, line_count)
    all_functions: list[tuple[str, str, str, str, int]] = []

    for repo in config_loader.get_enabled_repos():
        label     = repo["name"]
        clone_dir = (project_root / repo["local_path"]).resolve()

        if label not in ready_repos:
            print(f"  [SKIP] {label} — repo unavailable")
            continue

        for module in config_loader.get_enabled_modules(label):
            candidates = module.get("path_candidates", [module.get("path", "")])
            module_dir = _locate_module(clone_dir, candidates, module["name"])
            if module_dir is None:
                continue

            module_count = 0
            for py_file in module_dir.rglob("*.py"):
                rel_path = str(py_file.relative_to(clone_dir))
                for fn_name, fn_source, fn_lines in _extract_functions(
                    py_file, min_lines=min_lines
                ):
                    all_functions.append(
                        (fn_name, fn_source, rel_path, module["name"], fn_lines)
                    )
                    module_count += 1

            print(f"  {module['name']}: {module_count} qualifying functions found")

    total_found = len(all_functions)
    to_process  = min(total_found, max_functions)

    print(f"\n  Total qualifying functions : {total_found}")
    print(f"  Will process              : {to_process}  (max_functions={max_functions})")

    if not dry_run:
        estimated = to_process * _COST_PER_FUNCTION
        print(f"  Estimated cost            : ${estimated:.2f}")
        if estimated >= cost_warning:
            print(
                f"  [COST WARNING] Estimated cost ${estimated:.2f} exceeds "
                f"threshold ${cost_warning:.2f} — proceeding."
            )

    if dry_run:
        print("\n  DRY RUN complete — no changes made.")
        return 0

    # ── API calls and ChromaDB storage ────────────────────────────────────────
    client             = anthropic.Anthropic()
    total_chunks_added = 0
    processed          = 0
    cost_so_far        = 0.0

    for fn_name, fn_source, rel_path, module_label, line_count in all_functions[:to_process]:

        commentary_text_raw = _generate_commentary(
            client, fn_name, rel_path, module_label,
            fn_source, model, max_tokens,
        )

        if commentary_text_raw is None:
            time.sleep(api_delay)
            continue

        commentary_text = (
            f"Function: {fn_name}\n"
            f"File: {rel_path}\n"
            f"Module: {module_label}\n\n"
            f"{commentary_text_raw}"
        )

        added_c = store.add(
            texts=[commentary_text],
            metadatas=[{
                "source":              "code_commentary",
                "file_path":           rel_path,
                "function_name":       fn_name,
                "module":              module_label,
                "chunk_type":          "commentary",
                "generated_by":        model,
                "original_code_lines": line_count,
            }],
            ids=[_commentary_id(rel_path, fn_name)],
        )
        total_chunks_added += added_c

        added_r = store.add(
            texts=[fn_source],
            metadatas=[{
                "source":              "code_commentary",
                "file_path":           rel_path,
                "function_name":       fn_name,
                "module":              module_label,
                "chunk_type":          "raw_code",
                "generated_by":        model,
                "original_code_lines": line_count,
            }],
            ids=[_raw_code_id(rel_path, fn_name)],
        )
        total_chunks_added += added_r

        processed   += 1
        cost_so_far  = processed * _COST_PER_FUNCTION

        if processed % 10 == 0:
            print(
                f"  Processed {processed}/{to_process} functions"
                f" — estimated cost so far: ${cost_so_far:.2f}"
            )

        time.sleep(api_delay)

    print("\n  Commentary complete:")
    print(f"    Functions processed : {processed}")
    print(f"    Chunks added        : {total_chunks_added}")
    print(f"    Estimated cost      : ${cost_so_far:.2f}")

    return total_chunks_added

"""
week2/sources/code_commentary_ingester.py
Reads Python functions from ERPNext and Frappe HRMS source code, generates
plain-English commentary via the Claude API, and stores both commentary and
raw code in ChromaDB.

Repos used
----------
  ERPNext  — https://github.com/frappe/erpnext.git
             -> week2/data/erpnext_repo  (buying, projects)
  Frappe HRMS — https://github.com/frappe/hrms.git
             -> week2/data/hrms_repo     (hr, payroll)

Note: HR and Payroll were split out of the ERPNext monorepo into the
separate frappe/hrms app in ERPNext v14. They no longer exist in erpnext/hr
or erpnext/payroll.

Excluded from commentary (cost control)
-----------------------------------------
  erpnext/stock    — 150+ files, complex valuation & perpetual-inventory
                     logic; too expensive and noisy for a demo run.
  erpnext/accounts — similar scale and depth.

Public API
----------
    from sources.code_commentary_ingester import run
    chunks_added = run(store, config, dry_run=False, max_functions=999)
"""

from __future__ import annotations

import ast
import hashlib
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
# Repo configurations
# ---------------------------------------------------------------------------

# Maps relative repo path -> git clone URL
_REPO_URLS: dict[str, str] = {
    "week2/data/erpnext_repo": "https://github.com/frappe/erpnext.git",
    "week2/data/hrms_repo":    "https://github.com/frappe/hrms.git",
}

# Each entry targets one Python package sub-module.
#   repo_path  — relative path from project root to the cloned repo dir
#   module     — path inside the package root to the module folder
#   label      — human-readable name used in progress messages
_DEFAULT_MODULE_SPECS: list[dict] = [
    {
        "repo_path": "week2/data/erpnext_repo",
        "module":    "erpnext/buying",
        "label":     "buying",
    },
    {
        "repo_path": "week2/data/erpnext_repo",
        "module":    "erpnext/projects",
        "label":     "projects",
    },
    {
        "repo_path": "week2/data/hrms_repo",
        "module":    "hrms/hr",
        "label":     "hr",
    },
    {
        "repo_path": "week2/data/hrms_repo",
        "module":    "hrms/payroll",
        "label":     "payroll",
    },
]

# Cost estimate for claude-sonnet-4-6 (input $3/MTok, output $15/MTok).
# Average function: ~300 input tokens + ~200 output tokens ≈ $0.004 each.
_COST_PER_FUNCTION: float = 0.004

_MIN_FUNCTION_LINES: int = 5    # skip trivial one-liners and property wrappers
_API_DELAY: float = 0.5         # seconds between API calls (rate-limit buffer)


# ---------------------------------------------------------------------------
# Repo helpers
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    return shutil.which("git") is not None


def _clone_repo(clone_dir: Path, url: str, label: str) -> bool:
    """Shallow-clone *url* into *clone_dir*. Returns True on success."""
    if not _git_available():
        print(
            "  [ERROR] 'git' command not found.\n"
            "          Install Git then re-run."
        )
        return False

    print(f"  Cloning {label} repo (shallow) into {clone_dir} ...")
    print("  This may take 1-5 minutes depending on your connection.")
    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--single-branch",
                "--config", "core.protectNTFS=false",  # Windows NTFS safety
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
        print(f"  [ERROR] git clone timed out after 10 minutes ({label}).")
        return False
    except Exception as exc:
        print(f"  [ERROR] Unexpected error cloning {label}: {exc}")
        return False


def _find_package_root(clone_dir: Path, package_name: str) -> Path:
    """
    Return the directory that directly contains *package_name*/__init__.py.

    Handles two common layouts:
      clone_dir/{package_name}/__init__.py       (standard direct clone)
      clone_dir/{subdir}/{package_name}/__init__.py  (nested checkout)

    Falls back to clone_dir unchanged so callers get a clear "not found"
    warning rather than a silent wrong path.
    """
    if (clone_dir / package_name / "__init__.py").exists():
        return clone_dir

    for subdir in sorted(clone_dir.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("."):
            if (subdir / package_name / "__init__.py").exists():
                return subdir

    return clone_dir


def _find_module_dir(package_root: Path, module_path: str) -> Path | None:
    """
    Resolve *module_path* relative to *package_root*, trying two layouts:

    Primary  : package_root / module_path          (e.g. .../hrms/hr)
    Fallback : package_root / parts[0] / module    (e.g. .../hrms/hrms/hr)

    The fallback handles repos where the package sits one directory deeper
    than _find_package_root detected (e.g. hrms/hrms/ inside an hrms/ repo).

    Returns the resolved Path or None if neither location exists.
    """
    primary = package_root / module_path
    if primary.exists():
        return primary

    # Fallback: insert the top-level package name as an extra directory
    parts = Path(module_path).parts          # ('hrms', 'hr')
    if len(parts) >= 2:
        alt = package_root / parts[0] / module_path   # hrms/hrms/hr
        if alt.exists():
            print(f"  [INFO] Using alternative path: {alt}")
            return alt

    return None


# ---------------------------------------------------------------------------
# AST function extraction
# ---------------------------------------------------------------------------


def _extract_functions(file_path: Path) -> list[tuple[str, str, int]]:
    """
    Parse one .py file; return (name, source_code, line_count) for every
    qualifying FunctionDef.

    Excluded:
    - Fewer than _MIN_FUNCTION_LINES lines  (too trivial)
    - Dunder methods  __name__              (infrastructure, not business logic)
    - Names starting with test_             (test helpers)
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
    module_label: str,
    source_code: str,
) -> str | None:
    """Call Claude and return commentary text, or None on failure."""
    user_message = (
        f"Function name: {function_name}\n"
        f"File: {file_path}\n"
        f"Module: {module_label}\n\n"
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
    Generate AI commentary for Python functions from ERPNext + HRMS.

    Parameters
    ----------
    store : ChromaStore
        Destination knowledge base.
    config : dict
        CONFIG dict from week2/config.py.
    dry_run : bool
        If True, scan and report without calling the API or storing anything.
    max_functions : int
        Cap on functions to process (default 999). Set to 20 for a test run.

    Returns
    -------
    int
        Total chunks added (0 in dry_run mode).
    """
    project_root = Path(__file__).parent.parent.parent

    # ── Step 1: ensure all repos are cloned ──────────────────────────────────
    print("  Checking repositories ...")

    # Collect the unique repos referenced by the module specs.
    seen_repos: dict[str, Path] = {}   # repo_path_str -> absolute Path
    for spec in _DEFAULT_MODULE_SPECS:
        rp = spec["repo_path"]
        if rp not in seen_repos:
            seen_repos[rp] = (project_root / rp).resolve()

    repo_ok: set[str] = set()   # repo_path_str values that are ready

    for repo_path_str, clone_dir in seen_repos.items():
        label = Path(repo_path_str).name.replace("_repo", "")

        if clone_dir.exists() and any(clone_dir.iterdir()):
            print(f"  Repo already present: {clone_dir.name}")
            repo_ok.add(repo_path_str)
            continue

        if dry_run:
            # Don't attempt a clone in dry-run — report as unavailable.
            print(f"  [DRY RUN] Repo not found: {clone_dir}")
            print(f"            Run `python week2/ingest.py --source code` first.")
            continue

        url = _REPO_URLS.get(repo_path_str)
        if url is None:
            print(f"  [ERROR] No clone URL configured for {repo_path_str}")
            continue

        if _clone_repo(clone_dir, url, label):
            repo_ok.add(repo_path_str)

    # ── Step 2: resolve package roots and module directories ─────────────────
    print()
    package_roots: dict[str, Path] = {}   # repo_path_str -> package_root

    for repo_path_str, clone_dir in seen_repos.items():
        if repo_path_str not in repo_ok:
            continue

        # Infer package name from the first spec that uses this repo
        pkg_name = next(
            (Path(s["module"]).parts[0]
             for s in _DEFAULT_MODULE_SPECS
             if s["repo_path"] == repo_path_str),
            None,
        )
        if pkg_name is None:
            continue

        root = _find_package_root(clone_dir, pkg_name)
        package_roots[repo_path_str] = root
        print(f"  Package root ({pkg_name}): {root}")

    if dry_run:
        print("  DRY RUN — no API calls will be made, nothing stored.\n")

    # ── Step 3: collect qualifying functions across all target modules ────────
    # Tuple layout: (fn_name, fn_source, rel_path, label, line_count)
    all_functions: list[tuple[str, str, str, str, int]] = []

    for spec in _DEFAULT_MODULE_SPECS:
        rp    = spec["repo_path"]
        label = spec["label"]

        if rp not in package_roots:
            print(f"  [SKIP] {label} — repo unavailable")
            continue

        package_root = package_roots[rp]
        module_dir   = _find_module_dir(package_root, spec["module"])

        if module_dir is None:
            print(
                f"  [WARN] Module not found: {spec['module']} "
                f"(tried primary and fallback paths) — skipping {label}"
            )
            continue

        py_files     = list(module_dir.rglob("*.py"))
        module_count = 0

        for py_file in py_files:
            rel_path = str(py_file.relative_to(package_root))
            for fn_name, fn_source, fn_lines in _extract_functions(py_file):
                all_functions.append(
                    (fn_name, fn_source, rel_path, label, fn_lines)
                )
                module_count += 1

        print(f"  {label}: {module_count} qualifying functions found")

    total_found = len(all_functions)
    to_process  = min(total_found, max_functions)

    print(f"\n  Total qualifying functions : {total_found}")
    print(f"  Will process              : {to_process}  (max_functions={max_functions})")

    if not dry_run:
        print(f"  Estimated cost            : ${to_process * _COST_PER_FUNCTION:.2f}")

    if dry_run:
        print("\n  DRY RUN complete — no changes made.")
        return 0

    # ── Step 4: API calls and ChromaDB storage ────────────────────────────────
    client            = anthropic.Anthropic()
    total_chunks_added = 0
    processed         = 0
    cost_so_far       = 0.0

    for fn_name, fn_source, rel_path, label, line_count in all_functions[:to_process]:

        commentary = _generate_commentary(
            client, fn_name, rel_path, label, fn_source
        )

        if commentary is None:
            time.sleep(_API_DELAY)
            continue

        commentary_text = (
            f"Function: {fn_name}\n"
            f"File: {rel_path}\n"
            f"Module: {label}\n\n"
            f"{commentary}"
        )

        added_c = store.add(
            texts=[commentary_text],
            metadatas=[{
                "source":              "code_commentary",
                "file_path":           rel_path,
                "function_name":       fn_name,
                "module":              label,
                "chunk_type":          "commentary",
                "generated_by":        "claude-sonnet-4-6",
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
                "module":              label,
                "chunk_type":          "raw_code",
                "generated_by":        "claude-sonnet-4-6",
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

        time.sleep(_API_DELAY)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n  Commentary complete:")
    print(f"    Functions processed : {processed}")
    print(f"    Chunks added        : {total_chunks_added}")
    print(f"    Estimated cost      : ${cost_so_far:.2f}")

    return total_chunks_added

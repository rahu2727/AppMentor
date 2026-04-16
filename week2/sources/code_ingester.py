"""
week2/sources/code_ingester.py
Clones the ERPNext GitHub repository and ingests Python source files
and DocType JSON definitions into the ChromaStore knowledge base.

Strategy
--------
1. Clone https://github.com/frappe/erpnext.git (shallow, depth=1) into
   config["code"]["clone_dir"].  Skip the clone if the directory already
   exists (assume it was cloned previously).
2. Walk each module path in config["code"]["target_modules"].
3. For *.py files: split on top-level ``def`` / ``class`` boundaries.
   Each chunk must be >= 100 characters; max 200 chunks per file.
4. For *.json files inside a ``doctype`` directory: parse the DocType
   schema and convert it to a human-readable text summary.
5. Add all chunks with appropriate metadata.

Public API
----------
    from sources.code_ingester import run
    chunks_added = run(store, config)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from store.chroma_store import ChromaStore

_ERPNEXT_REPO_URL = "https://github.com/frappe/erpnext.git"
_MIN_CHUNK_CHARS  = 100
_MAX_CHUNKS_FILE  = 200


# ---------------------------------------------------------------------------
# Git clone
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    """Return True if the ``git`` command is on the PATH."""
    return shutil.which("git") is not None


def _clone_repo(clone_dir: Path) -> bool:
    """
    Shallow-clone the ERPNext repo into *clone_dir*.

    Returns True on success, False on any failure.
    Prints a helpful message if git is missing or the clone fails.
    """
    if not _git_available():
        print(
            "  [ERROR] 'git' command not found.\n"
            "          Install Git from https://git-scm.com/download/win\n"
            "          then re-run: python week2/ingest.py --source code"
        )
        return False

    print(f"  Cloning ERPNext repo (shallow) into {clone_dir} …")
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
            timeout=600,   # 10 minutes max
        )
        if result.returncode != 0:
            print(
                f"  [ERROR] git clone failed (exit {result.returncode}).\n"
                f"          {result.stderr.strip()}\n"
                f"  Check your internet connection and try again."
            )
            return False

        print(f"  Clone complete.")
        return True

    except subprocess.TimeoutExpired:
        print("  [ERROR] git clone timed out after 10 minutes.")
        return False
    except Exception as exc:
        print(f"  [ERROR] Unexpected error during git clone: {exc}")
        return False


# ---------------------------------------------------------------------------
# Python file chunking
# ---------------------------------------------------------------------------


def _split_by_definitions(content: str) -> list[str]:
    """
    Split Python source *content* into chunks at ``def`` / ``class`` boundaries.

    Any preamble before the first definition is kept as chunk 0 if it is
    long enough.  Each chunk must be >= _MIN_CHUNK_CHARS characters.
    Returns at most _MAX_CHUNKS_FILE chunks.
    """
    # Match 'def ' or 'class ' at the start of any line (any indentation)
    pattern = re.compile(r"^(def |class )", re.MULTILINE)
    positions = [m.start() for m in pattern.finditer(content)]

    if not positions:
        # No defs or classes — return the whole file as one chunk
        chunk = content.strip()
        return [chunk] if len(chunk) >= _MIN_CHUNK_CHARS else []

    chunks: list[str] = []

    # Preamble (imports, module-level constants, docstring)
    preamble = content[: positions[0]].strip()
    if len(preamble) >= _MIN_CHUNK_CHARS:
        chunks.append(preamble)

    boundaries = positions + [len(content)]
    for i in range(len(positions)):
        chunk = content[positions[i] : boundaries[i + 1]].strip()
        if len(chunk) >= _MIN_CHUNK_CHARS:
            chunks.append(chunk)

    return chunks[:_MAX_CHUNKS_FILE]


# ---------------------------------------------------------------------------
# DocType JSON → readable text
# ---------------------------------------------------------------------------


def _json_to_text(data: dict) -> str:
    """
    Convert an ERPNext DocType JSON schema to a human-readable text summary.

    Captures: name, module, description, fields, and roles.
    """
    lines: list[str] = []

    name = data.get("name", "Unknown DocType")
    lines.append(f"DocType: {name}")

    module = data.get("module", "")
    if module:
        lines.append(f"Module: {module}")

    description = data.get("description", "")
    if description:
        lines.append(f"Description: {description}")

    is_submittable = data.get("is_submittable", 0)
    if is_submittable:
        lines.append("Submittable: Yes (has Submit/Cancel/Amend workflow)")

    # Fields summary — skip layout-only field types
    _SKIP_TYPES = {"Column Break", "Section Break", "HTML", "Fold", "Heading"}
    fields = [
        f for f in data.get("fields", [])
        if f.get("fieldtype") not in _SKIP_TYPES and f.get("label")
    ]
    if fields:
        field_parts = [
            f"{f['label']} ({f.get('fieldtype', '?')})"
            for f in fields[:30]   # cap at 30 for readability
        ]
        lines.append(f"Fields: {', '.join(field_parts)}")

    # Roles
    permissions = data.get("permissions", [])
    roles = sorted({p.get("role", "") for p in permissions if p.get("role")})
    if roles:
        lines.append(f"Roles with access: {', '.join(roles[:15])}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------


def _chunk_id(file_path: str, index: int) -> str:
    """Deterministic MD5 ID from relative file path + chunk index."""
    key = f"{file_path}::{index}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Module walker
# ---------------------------------------------------------------------------


def _process_module(
    module_path: str,
    repo_root: Path,
    store: ChromaStore,
) -> int:
    """
    Walk all .py and doctype .json files in *module_path* inside *repo_root*.

    Returns total chunks added for this module.
    """
    module_dir = repo_root / module_path
    if not module_dir.exists():
        print(f"    [WARN] Module directory not found: {module_dir}")
        return 0

    py_files   = list(module_dir.rglob("*.py"))
    json_files = [
        p for p in module_dir.rglob("*.json")
        if "doctype" in p.parts   # only DocType definitions
    ]

    total_added = 0
    files_processed = 0

    # ── Python files ─────────────────────────────────────────────────────────
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if not content.strip():
            continue

        chunks = _split_by_definitions(content)
        if not chunks:
            continue

        rel_path = str(py_file.relative_to(repo_root))
        texts, metas, ids = [], [], []

        for i, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append(
                {
                    "source":    "code",
                    "file_type": "python",
                    "module":    module_path,
                    "file_path": rel_path,
                }
            )
            ids.append(_chunk_id(rel_path, i))

        added = store.add(texts=texts, metadatas=metas, ids=ids)
        total_added    += added
        files_processed += 1

    # ── DocType JSON files ────────────────────────────────────────────────────
    for json_file in json_files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, Exception):
            continue

        # Only process actual DocType definitions
        if data.get("doctype") != "DocType":
            continue

        text = _json_to_text(data)
        if len(text) < _MIN_CHUNK_CHARS:
            continue

        rel_path = str(json_file.relative_to(repo_root))
        added = store.add(
            texts=[text],
            metadatas=[
                {
                    "source":    "code",
                    "file_type": "json_doctype",
                    "module":    module_path,
                    "file_path": rel_path,
                }
            ],
            ids=[_chunk_id(rel_path, 0)],
        )
        total_added    += added
        files_processed += 1

    print(
        f"    {module_path}: {files_processed} file(s), "
        f"{total_added} chunks added."
    )
    return total_added


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(store: ChromaStore, config: dict) -> int:
    """
    Clone (or reuse) the ERPNext repo and ingest code chunks into *store*.

    Parameters
    ----------
    store : ChromaStore
        Destination knowledge base.
    config : dict
        The CONFIG dict from week2/config.py.

    Returns
    -------
    int
        Total chunks added.
    """
    clone_dir_str: str  = config.get("code", {}).get("clone_dir", "./week2/data/erpnext_repo")
    target_modules: list[str] = config.get("code", {}).get("target_modules", [])

    # Resolve clone_dir relative to the project root (where ingest.py lives)
    # so it works regardless of the caller's working directory.
    project_root = Path(__file__).parent.parent.parent   # AppMentor/
    clone_dir    = (project_root / clone_dir_str).resolve()

    # ── Clone if needed ───────────────────────────────────────────────────────
    if clone_dir.exists() and any(clone_dir.iterdir()):
        print(f"  Repo already present at {clone_dir} — skipping clone.")
    else:
        success = _clone_repo(clone_dir)
        if not success:
            return 0

    # ── Walk each target module ───────────────────────────────────────────────
    total_added = 0
    for module in target_modules:
        print(f"  Processing module: {module}")
        total_added += _process_module(module, clone_dir, store)

    return total_added

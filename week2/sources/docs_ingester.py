"""
week2/sources/docs_ingester.py
Ingests ERPNext documentation by cloning the GitHub markdown repo.

Why GitHub markdown instead of scraping docs.erpnext.com?
----------------------------------------------------------
docs.erpnext.com is a JavaScript-rendered SPA.  A plain ``requests``
call sees only an empty shell — no real content is in the static HTML.
The same documentation is published as plain markdown files on GitHub
and is fully readable by a simple file walk.

Strategy (three tiers, first success wins)
-----------------------------------------
1. Clone https://github.com/frappe/erpnext_documentation.git
   → week2/data/erpnext_docs
2. If that fails, try https://github.com/frappe/frappe_io.git
3. If both fail, fall back to fetching 20 known URLs with requests.

Public API
----------
    from sources.docs_ingester import run
    chunks_added = run(store, config)
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
    from bs4 import BeautifulSoup
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIMARY_CLONE_URL  = "https://github.com/frappe/erpnext_documentation.git"
_FALLBACK_CLONE_URL = "https://github.com/frappe/frappe_io.git"

# Resolve project root from this file's location
# week2/sources/docs_ingester.py  →  .parent.parent.parent = AppMentor/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_DEFAULT_CLONE_SUBPATH = os.path.join("week2", "data", "erpnext_docs")

# Folder names to focus on inside the cloned repo (checked in order)
_FOCUS_FOLDERS = [
    "erpnext",
    "hr",
    "accounts",
    "buying",
    "stock",
    "projects",
    "payroll",
]

_MD_EXTENSIONS = {".md", ".txt"}
_SKIP_STEMS    = {"readme", "index"}   # lowercased file stems to skip
_MIN_CHARS     = 200                   # ignore files shorter than this

# Hardcoded fallback URLs used when both git clones fail
_FALLBACK_URLS: list[tuple[str, str]] = [
    # (url, section_label)
    ("https://docs.erpnext.com/docs/user/manual/en/human-resources/leave-application",   "hr"),
    ("https://docs.erpnext.com/docs/user/manual/en/human-resources/expense-claim",        "hr"),
    ("https://docs.erpnext.com/docs/user/manual/en/human-resources/salary-slip",          "hr"),
    ("https://docs.erpnext.com/docs/user/manual/en/human-resources/payroll-entry",        "hr"),
    ("https://docs.erpnext.com/docs/user/manual/en/human-resources/employee",             "hr"),
    ("https://docs.erpnext.com/docs/user/manual/en/accounts/purchase-invoice",            "accounts"),
    ("https://docs.erpnext.com/docs/user/manual/en/accounts/sales-invoice",               "accounts"),
    ("https://docs.erpnext.com/docs/user/manual/en/accounts/journal-entry",               "accounts"),
    ("https://docs.erpnext.com/docs/user/manual/en/accounts/bank-reconciliation",         "accounts"),
    ("https://docs.erpnext.com/docs/user/manual/en/buying/purchase-order",                "buying"),
    ("https://docs.erpnext.com/docs/user/manual/en/buying/material-request",              "buying"),
    ("https://docs.erpnext.com/docs/user/manual/en/buying/request-for-quotation",         "buying"),
    ("https://docs.erpnext.com/docs/user/manual/en/stock/stock-entry",                   "stock"),
    ("https://docs.erpnext.com/docs/user/manual/en/stock/stock-reconciliation",           "stock"),
    ("https://docs.erpnext.com/docs/user/manual/en/stock/warehouse",                      "stock"),
    ("https://docs.erpnext.com/docs/user/manual/en/projects/project",                     "projects"),
    ("https://docs.erpnext.com/docs/user/manual/en/projects/task",                        "projects"),
    ("https://docs.erpnext.com/docs/user/manual/en/projects/timesheet",                   "projects"),
    ("https://docs.erpnext.com/docs/user/manual/en/CRM/lead",                             "crm"),
    ("https://docs.erpnext.com/docs/user/manual/en/setting-up/workflows",                 "setting-up"),
]

_REQUEST_TIMEOUT = 30     # seconds per HTTP request
_REQUEST_DELAY   = 1.5    # seconds between requests
_CLONE_TIMEOUT   = 600    # seconds for git clone (10 minutes)
_PROGRESS_EVERY  = 50     # print a progress line every N files


# ---------------------------------------------------------------------------
# Git clone helpers
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    return shutil.which("git") is not None


def _clone_repo(url: str, clone_dir: Path) -> bool:
    """
    Shallow-clone *url* into *clone_dir*.  Returns True on success.
    Never raises; prints a human-readable message on failure.
    """
    if not _git_available():
        print(
            "  [ERROR] 'git' not found on PATH.\n"
            "          Install Git: https://git-scm.com/download/win"
        )
        return False

    os.makedirs(str(clone_dir.parent), exist_ok=True)

    print(f"  Cloning ERPNext documentation from GitHub...")
    print(f"  {url}")

    try:
        result = subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--single-branch",
                url,
                str(clone_dir),
            ],
            capture_output=True,
            text=True,
            timeout=_CLONE_TIMEOUT,
        )
        if result.returncode == 0:
            print("  Clone complete.")
            return True

        print(
            f"  [WARN] git clone failed (exit {result.returncode}).\n"
            f"         {result.stderr.strip()}"
        )
        return False

    except subprocess.TimeoutExpired:
        print("  [WARN] git clone timed out after 10 minutes.")
        return False
    except Exception as exc:
        print(f"  [WARN] git clone error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _clean_markdown(text: str) -> str:
    """
    Remove markdown formatting characters while keeping all words.

    Converts:
      [link text](url)   →  link text
      ![alt](url)        →  alt
    Then strips: # * _ ` [ ]
    Finally collapses excess whitespace.
    """
    # Inline links  [text](url) → text
    text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)
    # Images  ![alt](url) → alt
    text = re.sub(r'!\[([^\]]*)\]\([^\)]*\)', r'\1', text)
    # Replace formatting characters with a space
    for ch in ('#', '*', '_', '`', '[', ']'):
        text = text.replace(ch, ' ')
    # Collapse multiple spaces on a single line
    text = re.sub(r'[ \t]{2,}', ' ', text)
    # Collapse more than two consecutive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _get_title(content: str) -> str:
    """Return the first non-empty line, stripped of leading # characters."""
    for line in content.splitlines():
        line = line.strip()
        if line:
            return line.lstrip('#').strip() or "Untitled"
    return "Untitled"


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Character-based chunking with overlap. Drops empty chunks."""
    chunks: list[str] = []
    start  = 0
    length = len(text)
    while start < length:
        end   = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start += chunk_size - chunk_overlap
    return chunks


def _chunk_id(file_path: str, index: int) -> str:
    """Deterministic MD5 ID: md5(file_path + '::' + str(index))."""
    key = f"{file_path}::{index}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# File collection helpers
# ---------------------------------------------------------------------------


def _in_hidden_dir(path: Path) -> bool:
    """Return True if any component of *path* starts with '.'."""
    return any(part.startswith('.') for part in path.parts)


def _should_process(filepath: Path) -> bool:
    """Return True if *filepath* should be ingested."""
    if _in_hidden_dir(filepath):
        return False
    if filepath.stem.lower() in _SKIP_STEMS:
        return False
    return True


def _collect_md_files(clone_dir: Path) -> list[Path]:
    """
    Return a sorted, deduplicated list of .md/.txt files to ingest.

    Prefers files inside _FOCUS_FOLDERS.  Falls back to a full repo walk
    if none of the focus folders exist.
    """
    focus_files: set[Path] = set()

    for folder_name in _FOCUS_FOLDERS:
        for folder in clone_dir.rglob(folder_name):
            if not folder.is_dir():
                continue
            if _in_hidden_dir(folder.relative_to(clone_dir)):
                continue
            for ext in _MD_EXTENSIONS:
                focus_files.update(folder.rglob(f"*{ext}"))

    if focus_files:
        all_files = focus_files
    else:
        # No recognised folders — walk the whole repo
        all_files = set()
        for ext in _MD_EXTENSIONS:
            all_files.update(clone_dir.rglob(f"*{ext}"))

    return sorted(f for f in all_files if _should_process(f))


# ---------------------------------------------------------------------------
# Markdown repo ingestion
# ---------------------------------------------------------------------------


def _ingest_markdown_repo(clone_dir: Path, store: ChromaStore, config: dict) -> int:
    """
    Walk the cloned repo, clean and chunk every eligible markdown file,
    and add them to *store*.  Returns total chunks added.
    """
    chunk_size:    int = config.get("chunking", {}).get("chunk_size",    1200)
    chunk_overlap: int = config.get("chunking", {}).get("chunk_overlap", 200)

    md_files = _collect_md_files(clone_dir)
    print(f"  Found {len(md_files)} markdown/text files to process.")

    if not md_files:
        print("  [WARN] No eligible files found in the cloned repository.")
        return 0

    total_added = 0

    for i, filepath in enumerate(md_files):
        # Progress update every _PROGRESS_EVERY files
        if i > 0 and i % _PROGRESS_EVERY == 0:
            print(f"  ... {i}/{len(md_files)} files processed, {total_added} chunks so far ...")

        # Read file
        try:
            raw = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if len(raw) < _MIN_CHARS:
            continue

        # Clean and extract
        title   = _get_title(raw)
        cleaned = _clean_markdown(raw)

        if len(cleaned) < _MIN_CHARS:
            continue

        # Chunk
        chunks = _chunk_text(cleaned, chunk_size, chunk_overlap)
        if not chunks:
            continue

        # Relative path for metadata and IDs (use forward slashes for
        # cross-platform determinism in the ID hash)
        try:
            rel_path = filepath.relative_to(clone_dir).as_posix()
        except ValueError:
            rel_path = filepath.name

        texts, metas, ids = [], [], []
        for idx, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append(
                {
                    "source":     "docs",
                    "file_path":  rel_path,
                    "file_type":  "markdown",
                    "page_title": title,
                }
            )
            ids.append(_chunk_id(rel_path, idx))

        added = store.add(texts=texts, metadatas=metas, ids=ids)
        total_added += added

    print(f"  Processed {len(md_files)} files → {total_added} chunks added.")
    return total_added


# ---------------------------------------------------------------------------
# Requests-based fallback
# ---------------------------------------------------------------------------


def _fetch_fallback_urls(store: ChromaStore, config: dict) -> int:
    """
    Last-resort ingestion: fetch _FALLBACK_URLS with requests + BeautifulSoup.
    Note: docs.erpnext.com is JS-rendered so content may be limited.
    Returns total chunks added.
    """
    if not _REQUESTS_OK:
        print(
            "  [SKIP] Fallback requires 'requests' and 'beautifulsoup4'.\n"
            "         pip install requests beautifulsoup4"
        )
        return 0

    chunk_size:    int = config.get("chunking", {}).get("chunk_size",    1200)
    chunk_overlap: int = config.get("chunking", {}).get("chunk_overlap", 200)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    session     = requests.Session()
    total_added = 0
    total       = len(_FALLBACK_URLS)

    print(f"  Fallback mode: fetching {total} known URLs with requests ...")

    for n, (url, section) in enumerate(_FALLBACK_URLS, 1):
        print(f"  [{n:2d}/{total}] {url}")

        try:
            resp = session.get(url, headers=headers, timeout=_REQUEST_TIMEOUT,
                               allow_redirects=True)
            if resp.status_code != 200:
                print(f"           [SKIP] HTTP {resp.status_code}")
                time.sleep(_REQUEST_DELAY)
                continue
        except requests.exceptions.ConnectionError:
            print("           [SKIP] connection error")
            time.sleep(_REQUEST_DELAY)
            continue
        except requests.exceptions.Timeout:
            print("           [SKIP] timed out")
            time.sleep(_REQUEST_DELAY)
            continue
        except Exception as exc:
            print(f"           [SKIP] {exc}")
            time.sleep(_REQUEST_DELAY)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        container = soup.find("article") or soup.find("main") or soup.body
        text = (container or soup).get_text(separator=" ", strip=True)

        if len(text) < _MIN_CHARS:
            print(f"           [SKIP] too little text ({len(text)} chars)")
            time.sleep(_REQUEST_DELAY)
            continue

        # Page title
        title = "Untitled"
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

        chunks = _chunk_text(text, chunk_size, chunk_overlap)
        texts, metas, ids = [], [], []

        for idx, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append(
                {
                    "source":     "docs",
                    "url":        url,
                    "file_type":  "html",
                    "section":    section,
                    "page_title": title,
                }
            )
            ids.append(_chunk_id(url, idx))

        added = store.add(texts=texts, metadatas=metas, ids=ids)
        total_added += added
        print(f"           '{title}' → {added} chunk(s)")
        time.sleep(_REQUEST_DELAY)

    return total_added


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(store: ChromaStore, config: dict) -> int:
    """
    Ingest ERPNext documentation into *store*.

    Tries three strategies in order:
    1. Clone frappe/erpnext_documentation → walk markdown files
    2. Clone frappe/frappe_io             → walk markdown files
    3. Fetch 20 hardcoded URLs with requests

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
    # Resolve clone directory
    clone_subpath = config.get("docs", {}).get(
        "clone_dir",
        _DEFAULT_CLONE_SUBPATH,
    )
    clone_dir = (_PROJECT_ROOT / clone_subpath).resolve()

    # ── Step 1: ensure we have the repo cloned ────────────────────────────────
    already_cloned = clone_dir.exists() and any(clone_dir.iterdir())

    if already_cloned:
        print(f"  Docs repo already present at {clone_dir} — skipping clone.")
        use_markdown = True
    else:
        # Try primary URL
        success = _clone_repo(_PRIMARY_CLONE_URL, clone_dir)

        if not success:
            # Clean up any partial clone directory before retrying
            if clone_dir.exists():
                shutil.rmtree(str(clone_dir), ignore_errors=True)

            print(f"  Trying fallback clone URL ...")
            success = _clone_repo(_FALLBACK_CLONE_URL, clone_dir)

        use_markdown = success

    # ── Step 2: ingest ────────────────────────────────────────────────────────
    if use_markdown:
        return _ingest_markdown_repo(clone_dir, store, config)
    else:
        print("  Both git clones failed — using requests fallback.")
        return _fetch_fallback_urls(store, config)

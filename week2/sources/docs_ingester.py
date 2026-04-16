"""
week2/sources/docs_ingester.py
Fetches a hardcoded list of known ERPNext documentation pages and stores
text chunks in the ChromaStore knowledge base.

Why hardcoded URLs?
-------------------
docs.erpnext.com renders its navigation with JavaScript. A plain
``requests`` call sees only a skeleton shell — no sub-page links are
present in the static HTML. Crawling from the index is therefore
unreliable.  Using explicit, known-good URLs gives stable, reproducible
results without requiring a headless browser.

Public API
----------
    from sources.docs_ingester import run
    chunks_added = run(store, config)
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
    from bs4 import BeautifulSoup
    _DEPS_OK = True
except ImportError as _e:
    _DEPS_OK = False
    _IMPORT_ERR = str(_e)

from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# Hardcoded list of known ERPNext documentation pages
# Each tuple: (url, section_label)
# ---------------------------------------------------------------------------

KNOWN_URLS: list[tuple[str, str]] = [
    # ── HR module ─────────────────────────────────────────────────────────────
    (
        "https://docs.erpnext.com/docs/user/manual/en/human-resources/leave-application",
        "hr",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/human-resources/expense-claim",
        "hr",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/human-resources/salary-slip",
        "hr",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/human-resources/employee",
        "hr",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/human-resources/payroll-entry",
        "hr",
    ),
    # ── Accounts module ───────────────────────────────────────────────────────
    (
        "https://docs.erpnext.com/docs/user/manual/en/accounts/purchase-invoice",
        "accounts",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/accounts/sales-invoice",
        "accounts",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/accounts/journal-entry",
        "accounts",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/accounts/bank-reconciliation",
        "accounts",
    ),
    # ── Buying module ─────────────────────────────────────────────────────────
    (
        "https://docs.erpnext.com/docs/user/manual/en/buying/purchase-order",
        "buying",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/buying/material-request",
        "buying",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/buying/request-for-quotation",
        "buying",
    ),
    # ── Stock module ──────────────────────────────────────────────────────────
    (
        "https://docs.erpnext.com/docs/user/manual/en/stock/stock-entry",
        "stock",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/stock/stock-reconciliation",
        "stock",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/stock/warehouse",
        "stock",
    ),
    # ── Projects module ───────────────────────────────────────────────────────
    (
        "https://docs.erpnext.com/docs/user/manual/en/projects/project",
        "projects",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/projects/task",
        "projects",
    ),
    (
        "https://docs.erpnext.com/docs/user/manual/en/projects/timesheet",
        "projects",
    ),
]

_TIMEOUT = 30    # seconds — generous to allow for slow responses
_DELAY   = 1.5   # seconds between requests (polite crawl)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch(url: str, session: "requests.Session") -> "requests.Response | None":
    """
    GET *url* and return the Response, or None on any error.

    Handles ConnectionError and Timeout explicitly so the loop never crashes.
    Non-200 responses are also treated as None (skip silently).
    """
    try:
        resp = session.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        if resp.status_code != 200:
            return None
        return resp
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return None
    except Exception:
        return None


def _page_title(soup: "BeautifulSoup") -> str:
    """Return <title> text, first <h1>, or 'Untitled' as fallback."""
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def _extract_text(html: str) -> str:
    """
    Strip HTML and return clean plain text.

    Removes script, style, nav, header, footer first, then extracts
    text from <article> → <main> → <body> in priority order.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    container = soup.find("article") or soup.find("main") or soup.body
    if container is None:
        return soup.get_text(separator=" ", strip=True)

    return container.get_text(separator=" ", strip=True)


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    Split *text* into overlapping character-based chunks.
    Empty or whitespace-only chunks are discarded.
    """
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start += chunk_size - chunk_overlap
    return chunks


def _chunk_id(url: str, index: int) -> str:
    """Deterministic MD5 ID: md5(url + "::" + str(index))."""
    key = f"{url}::{index}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(store: ChromaStore, config: dict) -> int:
    """
    Fetch all KNOWN_URLS and ingest text chunks into *store*.

    Parameters
    ----------
    store : ChromaStore
        Destination knowledge base.
    config : dict
        The CONFIG dict from week2/config.py.  Uses config["chunking"]
        for chunk_size and chunk_overlap; other docs settings are
        superseded by the hardcoded URL list.

    Returns
    -------
    int
        Total chunks added.
    """
    if not _DEPS_OK:
        print(
            f"  [SKIP] docs ingester requires 'requests' and 'beautifulsoup4'.\n"
            f"         pip install requests beautifulsoup4\n"
            f"         Error: {_IMPORT_ERR}"
        )
        return 0

    chunk_size: int    = config.get("chunking", {}).get("chunk_size", 1200)
    chunk_overlap: int = config.get("chunking", {}).get("chunk_overlap", 200)

    session     = requests.Session()
    total_added = 0
    total_urls  = len(KNOWN_URLS)

    print(f"  Fetching {total_urls} known ERPNext documentation pages ...")

    for idx, (url, section) in enumerate(KNOWN_URLS, 1):
        print(f"  [{idx:2d}/{total_urls}] {url}")

        resp = _fetch(url, session)
        if resp is None:
            print(f"           [SKIP] no response or non-200 status")
            time.sleep(_DELAY)
            continue

        soup       = BeautifulSoup(resp.text, "html.parser")
        title      = _page_title(soup)
        clean_text = _extract_text(resp.text)

        if len(clean_text) < 80:
            print(f"           [SKIP] too little text ({len(clean_text)} chars)")
            time.sleep(_DELAY)
            continue

        chunks = _chunk_text(clean_text, chunk_size, chunk_overlap)

        texts, metas, ids = [], [], []
        for i, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append(
                {
                    "source":     "docs",
                    "url":        url,
                    "section":    section,
                    "page_title": title,
                }
            )
            ids.append(_chunk_id(url, i))

        added = store.add(texts=texts, metadatas=metas, ids=ids)
        total_added += added
        print(f"           '{title}' → {added} chunk(s)")

        time.sleep(_DELAY)

    print(f"\n  Done. {total_added} doc chunks added across {total_urls} pages.")
    return total_added

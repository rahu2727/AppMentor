"""
week2/sources/docs_ingester.py
Crawls docs.erpnext.com sections defined in CONFIG and ingests text chunks.

For each section the ingester:
  1. Fetches the section index page and collects sub-page links.
  2. Visits each sub-page (max 15 per section, 1.5 s delay between requests).
  3. Strips HTML with BeautifulSoup, splits into overlapping chunks.
  4. Stores each chunk in ChromaStore with source/url/section/page_title metadata.

Connection errors and non-200 responses are caught and skipped — the ingester
never crashes on a network failure.

Public API
----------
    from sources.docs_ingester import run
    chunks_added = run(store, config)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
    from bs4 import BeautifulSoup
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False

from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# Section-name → base URL mapping for docs.erpnext.com
# ---------------------------------------------------------------------------

_SECTION_BASE_URLS: dict[str, str] = {
    "hr":          "https://docs.erpnext.com/docs/user/manual/en/human-resources",
    "accounts":    "https://docs.erpnext.com/docs/user/manual/en/accounts",
    "projects":    "https://docs.erpnext.com/docs/user/manual/en/projects",
    "buying":      "https://docs.erpnext.com/docs/user/manual/en/buying",
    "stock":       "https://docs.erpnext.com/docs/user/manual/en/stock",
    "setting-up":  "https://docs.erpnext.com/docs/user/manual/en/setting-up",
}

_REQUEST_TIMEOUT = 10          # seconds per HTTP request
_DELAY_BETWEEN_REQUESTS = 1.5  # seconds (polite crawl)
_MAX_PAGES_PER_SECTION = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(url: str, session: "requests.Session") -> "requests.Response | None":
    """Fetch *url*, returning None on any error or non-200 status."""
    try:
        resp = session.get(url, timeout=_REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        return resp
    except Exception:
        return None


def _extract_text(html: str) -> str:
    """Strip HTML tags and return clean plain text."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove navigation, script, and style noise
    for tag in soup(["nav", "script", "style", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def _get_title(html: str) -> str:
    """Extract the page <title> or first <h1>."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def _collect_links(html: str, base_url: str) -> list[str]:
    """Return same-domain links found on the page."""
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        if urlparse(full).netloc == base_domain and full not in links:
            links.append(full)
    return links


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split *text* into overlapping chunks of roughly *chunk_size* chars."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += chunk_size - chunk_overlap
    return [c.strip() for c in chunks if c.strip()]


def _make_id(url: str, chunk_index: int) -> str:
    """Deterministic ID from URL + chunk position."""
    import hashlib
    key = f"{url}::{chunk_index}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Main ingester
# ---------------------------------------------------------------------------


def run(store: ChromaStore, config: dict) -> int:
    """
    Crawl docs.erpnext.com sections from *config* and ingest text chunks.

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
    if not _DEPS_AVAILABLE:
        print("  [SKIP] docs ingester requires 'requests' and 'beautifulsoup4'.")
        return 0

    sections: list[str] = config.get("docs", {}).get("sections", [])
    chunk_size: int = config.get("chunking", {}).get("chunk_size", 1200)
    chunk_overlap: int = config.get("chunking", {}).get("chunk_overlap", 200)

    session = requests.Session()
    session.headers["User-Agent"] = "AppMentor-ingester/1.0 (educational project)"

    total_added = 0

    for section in sections:
        base_url = _SECTION_BASE_URLS.get(section)
        if not base_url:
            print(f"  [SKIP] No URL mapping for section '{section}'.")
            continue

        print(f"  Crawling section: {section} ({base_url})")

        # Step 1: fetch the section index and collect page links
        resp = _get(base_url, session)
        if resp is None:
            print(f"    [WARN] Could not fetch index for '{section}'. Skipping.")
            continue

        time.sleep(_DELAY_BETWEEN_REQUESTS)
        links = _collect_links(resp.text, base_url)

        # Always include the index page itself
        pages_to_visit = [base_url] + [
            lnk for lnk in links if lnk != base_url
        ]
        pages_to_visit = pages_to_visit[:_MAX_PAGES_PER_SECTION]

        section_added = 0
        for page_url in pages_to_visit:
            page_resp = _get(page_url, session)
            if page_resp is None:
                continue

            page_title = _get_title(page_resp.text)
            text = _extract_text(page_resp.text)

            if len(text) < 100:
                # Too little content — skip (likely a redirect or nav page)
                time.sleep(_DELAY_BETWEEN_REQUESTS)
                continue

            chunks = _chunk_text(text, chunk_size, chunk_overlap)
            texts, metadatas, ids = [], [], []

            for i, chunk in enumerate(chunks):
                texts.append(chunk)
                metadatas.append(
                    {
                        "source": "docs",
                        "url": page_url,
                        "section": section,
                        "page_title": page_title,
                    }
                )
                ids.append(_make_id(page_url, i))

            added = store.add(texts=texts, metadatas=metadatas, ids=ids)
            section_added += added
            time.sleep(_DELAY_BETWEEN_REQUESTS)

        print(f"    Added {section_added} chunks from '{section}'.")
        total_added += section_added

    return total_added

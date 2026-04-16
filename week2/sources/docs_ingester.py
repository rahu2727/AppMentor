"""
week2/sources/docs_ingester.py
Crawls docs.erpnext.com sections defined in config["docs"]["sections"]
and stores text chunks in the ChromaStore knowledge base.

Crawl strategy
--------------
1. For each section name, resolve its base URL via SECTION_URLS.
2. Fetch the base URL, collect same-domain page links from the page.
3. Visit each linked page (up to max_pages_per_section) with a 1.5 s delay.
4. Extract clean text from <article>, <main>, <div class="content">, or
   fall back to <body>.  Remove script/style/nav/header/footer first.
5. Chunk the text with character-based overlap.
6. Add chunks to the store with source/url/section/page_title metadata.

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
from urllib.parse import urljoin, urlparse

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
# Section name → canonical docs.erpnext.com URL
# ---------------------------------------------------------------------------

SECTION_URLS: dict[str, str] = {
    "hr":         "https://docs.erpnext.com/docs/user/manual/en/human-resources",
    "accounts":   "https://docs.erpnext.com/docs/user/manual/en/accounts",
    "projects":   "https://docs.erpnext.com/docs/user/manual/en/projects",
    "buying":     "https://docs.erpnext.com/docs/user/manual/en/buying",
    "stock":      "https://docs.erpnext.com/docs/user/manual/en/stock",
    "setting-up": "https://docs.erpnext.com/docs/user/manual/en/setting-up",
}

_DELAY   = 1.5   # seconds between requests (polite crawl)
_TIMEOUT = 12    # seconds per request

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch(url: str, session: "requests.Session") -> "requests.Response | None":
    """
    GET *url* and return the Response, or None on any error.

    Silently swallows ConnectionError, Timeout, and non-200 status codes.
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
    """Return <title> text or first <h1>, falling back to 'Untitled'."""
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def _extract_text(html: str) -> str:
    """
    Strip HTML and return clean plain text.

    Priority for main content: <article> → <main> → <div class="content"> → <body>.
    Removes script, style, nav, header, footer noise first.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove noisy structural elements
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    # Try progressively broader containers
    container = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_="content")
        or soup.body
    )

    if container is None:
        return soup.get_text(separator=" ", strip=True)

    return container.get_text(separator=" ", strip=True)


def _collect_links(html: str, base_url: str) -> list[str]:
    """
    Return unique same-domain links from an HTML page, keeping only
    paths that start with the same path prefix as *base_url*.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_parsed = urlparse(base_url)
    domain = base_parsed.netloc
    base_path = base_parsed.path.rstrip("/")

    seen: set[str] = set()
    links: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0]   # strip anchors
        if not href:
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        # Same domain, same path prefix, no query parameters
        if (
            parsed.netloc == domain
            and parsed.path.startswith(base_path)
            and not parsed.query
            and full not in seen
        ):
            seen.add(full)
            links.append(full)

    return links


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    Split *text* into overlapping chunks of ~*chunk_size* characters.
    Empty or whitespace-only chunks are dropped.
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
    """Deterministic MD5 ID from page URL + chunk index."""
    key = f"{url}::{index}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(store: ChromaStore, config: dict) -> int:
    """
    Crawl docs.erpnext.com and ingest text chunks into *store*.

    Parameters
    ----------
    store : ChromaStore
        Destination knowledge base.
    config : dict
        The CONFIG dict from week2/config.py.

    Returns
    -------
    int
        Total chunks added across all sections.
    """
    if not _DEPS_OK:
        print(
            f"  [SKIP] docs ingester requires 'requests' and 'beautifulsoup4'.\n"
            f"         Install with: pip install requests beautifulsoup4\n"
            f"         Error: {_IMPORT_ERR}"
        )
        return 0

    sections: list[str]  = config.get("docs", {}).get("sections", [])
    max_pages: int        = config.get("docs", {}).get("max_pages_per_section", 15)
    chunk_size: int       = config.get("chunking", {}).get("chunk_size", 1200)
    chunk_overlap: int    = config.get("chunking", {}).get("chunk_overlap", 200)

    session = requests.Session()
    total_added = 0

    for section in sections:
        base_url = SECTION_URLS.get(section)
        if not base_url:
            print(f"  [WARN] No URL mapping for section '{section}' — skipping.")
            continue

        print(f"  Crawling section '{section}': {base_url}")

        # ── Step 1: fetch index page ───────────────────────────────────────
        resp = _fetch(base_url, session)
        if resp is None:
            print(f"    [WARN] Could not fetch index for '{section}' — skipping.")
            continue

        index_title = _page_title(BeautifulSoup(resp.text, "html.parser"))
        sub_links   = _collect_links(resp.text, base_url)

        # Always include the index page; sub-pages fill up to max_pages
        pages = [base_url] + [lnk for lnk in sub_links if lnk != base_url]
        pages = pages[:max_pages]

        time.sleep(_DELAY)

        # ── Step 2: visit each page ────────────────────────────────────────
        section_chunks = 0
        for page_num, page_url in enumerate(pages, 1):
            page_resp = _fetch(page_url, session)
            if page_resp is None:
                time.sleep(_DELAY)
                continue

            soup       = BeautifulSoup(page_resp.text, "html.parser")
            title      = _page_title(soup)
            clean_text = _extract_text(page_resp.text)

            if len(clean_text) < 80:
                # Too little content (redirect target, empty page, etc.)
                time.sleep(_DELAY)
                continue

            chunks = _chunk_text(clean_text, chunk_size, chunk_overlap)

            texts, metas, ids = [], [], []
            for i, chunk in enumerate(chunks):
                texts.append(chunk)
                metas.append(
                    {
                        "source":     "docs",
                        "url":        page_url,
                        "section":    section,
                        "page_title": title,
                    }
                )
                ids.append(_chunk_id(page_url, i))

            added = store.add(texts=texts, metadatas=metas, ids=ids)
            section_chunks += added
            time.sleep(_DELAY)

        print(f"    {page_num} page(s) crawled, {section_chunks} chunks added.")
        total_added += section_chunks

    return total_added

"""
week2/sources/docs_ingester.py
Fetches ERPNext/Frappe documentation from confirmed working URLs on
docs.frappe.io and ingests text chunks into the ChromaStore.

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

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from bs4 import BeautifulSoup

from store.chroma_store import ChromaStore

# ---------------------------------------------------------------------------
# Confirmed working URLs  (manually verified against docs.frappe.io)
# ---------------------------------------------------------------------------

DOCS_URLS: list[str] = [
    # ── HR module  (/hr/ prefix) ─────────────────────────────────────────────
    "https://docs.frappe.io/hr/expense-claim",
    "https://docs.frappe.io/hr/leave-application",
    "https://docs.frappe.io/hr/salary-slip",
    "https://docs.frappe.io/hr/payroll-entry",
    "https://docs.frappe.io/hr/employee",
    "https://docs.frappe.io/hr/attendance",
    "https://docs.frappe.io/hr/leave-type",
    "https://docs.frappe.io/hr/leave-policy",
    "https://docs.frappe.io/hr/leave-allocation",
    "https://docs.frappe.io/hr/leave-encashment",
    # ── Accounts  (/erpnext/ prefix) ─────────────────────────────────────────
    "https://docs.frappe.io/erpnext/purchase-invoice",
    "https://docs.frappe.io/erpnext/sales-invoice",
    "https://docs.frappe.io/erpnext/journal-entry",
    "https://docs.frappe.io/erpnext/bank-reconciliation",
    "https://docs.frappe.io/erpnext/payment-entry",
    "https://docs.frappe.io/erpnext/chart-of-accounts",
    # ── Buying ───────────────────────────────────────────────────────────────
    "https://docs.frappe.io/erpnext/purchase-order",
    "https://docs.frappe.io/erpnext/material-request",
    "https://docs.frappe.io/erpnext/supplier-quotation",
    "https://docs.frappe.io/erpnext/request-for-quotation",
    # ── Stock ────────────────────────────────────────────────────────────────
    "https://docs.frappe.io/erpnext/stock-entry",
    "https://docs.frappe.io/erpnext/warehouse",
    "https://docs.frappe.io/erpnext/stock-reconciliation",
    "https://docs.frappe.io/erpnext/delivery-note",
    "https://docs.frappe.io/erpnext/purchase-receipt",
    # ── Projects ─────────────────────────────────────────────────────────────
    "https://docs.frappe.io/erpnext/project",
    "https://docs.frappe.io/erpnext/task",
    "https://docs.frappe.io/erpnext/timesheet",
    # ── CRM ──────────────────────────────────────────────────────────────────
    "https://docs.frappe.io/erpnext/lead",
    "https://docs.frappe.io/erpnext/opportunity",
    # ── Setup ────────────────────────────────────────────────────────────────
    "https://docs.frappe.io/erpnext/workflows",
    "https://docs.frappe.io/erpnext/email-account",
    "https://docs.frappe.io/erpnext/user-permissions",
    "https://docs.frappe.io/erpnext/print-format",
]

_HEADERS  = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT  = 30    # seconds per request
_DELAY    = 1.5   # seconds between requests
_MIN_TEXT = 300   # skip pages with fewer chars of extracted text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_module(url: str) -> str:
    """Derive a module label from the URL path."""
    if "/hr/" in url:
        return "hr"
    return url.split("/erpnext/")[-1].split("/")[0]


def _extract_content(soup: BeautifulSoup) -> str:
    """
    Remove noise tags then return text from the best content container.

    Search order: article → main → div.doc-content → div.content →
                  div.main → body
    """
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    container = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=lambda c: c and "doc-content" in c)
        or soup.find("div", class_=lambda c: c and "content" in c)
        or soup.find("div", class_=lambda c: c and "main" in c)
        or soup.body
    )
    return (container or soup).get_text(separator=" ", strip=True)


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Character-based chunking with overlap. Drops empty chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end   = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += chunk_size - chunk_overlap
    return chunks


def _chunk_id(url: str, index: int) -> str:
    """md5(url + str(index)) → 32-char hex string."""
    return hashlib.md5((url + str(index)).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(store: ChromaStore, config: dict) -> int:
    """
    Fetch every URL in DOCS_URLS, chunk the content, and add to *store*.

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
    chunk_size:    int = config.get("chunking", {}).get("chunk_size",    1200)
    chunk_overlap: int = config.get("chunking", {}).get("chunk_overlap",  200)

    total      = len(DOCS_URLS)
    fetched    = 0
    skipped    = 0
    total_added = 0

    for i, url in enumerate(DOCS_URLS, 1):
        print(f"  Fetching [{i}/{total}] {url}")

        # ── HTTP request ──────────────────────────────────────────────────────
        try:
            response = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        except requests.exceptions.ConnectionError as exc:
            print(f"  [ERROR] connection error — {exc}")
            skipped += 1
            time.sleep(_DELAY)
            continue
        except requests.exceptions.Timeout:
            print(f"  [TIMEOUT] {url}")
            skipped += 1
            time.sleep(_DELAY)
            continue
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            skipped += 1
            time.sleep(_DELAY)
            continue

        if response.status_code != 200:
            print(f"  [SKIP] {url} — HTTP {response.status_code}")
            skipped += 1
            time.sleep(_DELAY)
            continue

        # ── Parse HTML ────────────────────────────────────────────────────────
        try:
            soup = BeautifulSoup(response.text, "html.parser")
            text = _extract_content(soup)
        except Exception as exc:
            print(f"  [ERROR] parse failed — {exc}")
            skipped += 1
            time.sleep(_DELAY)
            continue

        if len(text) < _MIN_TEXT:
            print(f"  [SKIP] {url} — only {len(text)} chars of text")
            skipped += 1
            time.sleep(_DELAY)
            continue

        # ── Metadata ─────────────────────────────────────────────────────────
        title_tag = soup.find("title")
        title     = title_tag.text.strip() if title_tag else url
        module    = _extract_module(url)

        # ── Chunk & store ─────────────────────────────────────────────────────
        chunks = _chunk_text(text, chunk_size, chunk_overlap)

        texts, metas, ids = [], [], []
        for idx, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append(
                {
                    "source":     "docs",
                    "url":        url,
                    "page_title": title[:200],
                    "module":     module,
                    "file_type":  "documentation",
                }
            )
            ids.append(_chunk_id(url, idx))

        added = store.add(texts, metas, ids)
        total_added += added
        fetched     += 1
        print(f"  [OK] {url} — {added} chunks added")

        time.sleep(_DELAY)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(
        f"\n  Docs complete: {fetched} URLs fetched, "
        f"{skipped} skipped, {total_added} chunks total"
    )
    return total_added

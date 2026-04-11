"""
week2/store/chroma_store.py — ChromaDB wrapper for the AppMentor knowledge base.

Public API:
    store = ChromaStore()
    store.add(documents, metadatas, ids)
    results = store.query(query_text, n_results)  # returns list of dicts
    count   = store.count()
    stats   = store.stats()   # breakdown by source
    store.reset()
"""

from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ---------------------------------------------------------------------------
# Import config — handle both "run from project root" and "run from week2/"
# ---------------------------------------------------------------------------
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHROMA_DIR, COLLECTION_NAME, DEFAULT_N_RESULTS, EMBEDDING_MODEL


class ChromaStore:
    """Thin wrapper around a ChromaDB PersistentClient collection."""

    def __init__(
        self,
        persist_dir: str | Path | None = None,
        collection_name: str = COLLECTION_NAME,
        embedding_model: str = EMBEDDING_MODEL,
    ) -> None:
        self._persist_dir = Path(persist_dir) if persist_dir else CHROMA_DIR
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(self._persist_dir))

        self._ef = SentenceTransformerEmbeddingFunction(model_name=embedding_model)

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """
        Upsert documents into the collection.

        Duplicate IDs are silently updated (ChromaDB upsert semantics).
        """
        if not documents:
            return
        self._collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        n_results: int = DEFAULT_N_RESULTS,
    ) -> list[dict[str, Any]]:
        """
        Semantic search against the collection.

        Returns a list of dicts, each containing:
            text      — the stored document string
            metadata  — the stored metadata dict
            distance  — cosine distance (0 = identical, 2 = opposite)
        """
        raw = self._collection.query(
            query_texts=[query_text],
            n_results=min(n_results, self._collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        results = []
        docs = raw["documents"][0]
        metas = raw["metadatas"][0]
        dists = raw["distances"][0]

        for doc, meta, dist in zip(docs, metas, dists):
            results.append({"text": doc, "metadata": meta, "distance": dist})

        return results

    def count(self) -> int:
        """Return total number of documents in the collection."""
        return self._collection.count()

    def stats(self) -> dict[str, Any]:
        """
        Return a summary of the collection broken down by source.

        Example return value:
            {
                "total": 42,
                "by_source": {
                    "forum": 20,
                    "docs": 15,
                    "code": 7,
                }
            }
        """
        total = self._collection.count()
        if total == 0:
            return {"total": 0, "by_source": {}}

        all_items = self._collection.get(include=["metadatas"])
        by_source: dict[str, int] = {}
        for meta in all_items["metadatas"]:
            source = meta.get("source", "unknown")
            by_source[source] = by_source.get(source, 0) + 1

        return {"total": total, "by_source": by_source}

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Delete all documents from the collection (keeps the collection itself)."""
        self._collection.delete(where={"source": {"$ne": "__impossible__"}})
        # Fallback: delete every id if the above returns nothing
        all_ids = self._collection.get()["ids"]
        if all_ids:
            self._collection.delete(ids=all_ids)

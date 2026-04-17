"""
week2/store/chroma_store.py — ChromaDB wrapper for AppMentor.

Uses SentenceTransformer directly so embeddings are produced locally,
independent of ChromaDB's built-in embedding-function helpers.

Public API
----------
    store = ChromaStore(persist_dir, collection_name, embedding_model)
    n     = store.add(texts, metadatas, ids)   -> int (chunks added)
    hits  = store.query(query_text, n_results, where)  -> list[dict]
    n     = store.count()                      -> int
    info  = store.stats()                      -> dict
    store.reset()
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

# Make week2/ importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent.parent))


class ChromaStore:
    """Thin wrapper around a ChromaDB PersistentClient collection."""

    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        embedding_model: str,
    ) -> None:
        self._persist_dir = persist_dir
        self._collection_name = collection_name

        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        # Persistent ChromaDB client — data survives process restarts
        self._client = chromadb.PersistentClient(path=str(persist_dir))

        # SentenceTransformer for local embeddings (no API key required)
        self._model = SentenceTransformer(embedding_model)

        # Get existing collection or create a new one with cosine similarity
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, texts: list[str], metadatas: list[dict], ids: list[str]) -> int:
        """
        Encode texts and upsert them into the collection.

        Uses upsert so re-running ingestion is safe (same ID = update).

        Returns
        -------
        int
            Number of chunks added/updated.
        """
        if not texts:
            return 0

        embeddings = self._model.encode(texts, show_progress_bar=False).tolist()

        self._collection.upsert(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
        return len(texts)

    def upsert(self, texts: list[str], metadatas: list[dict], ids: list[str]) -> int:
        """
        Explicit upsert — identical to add() but communicates idempotent intent.

        Preferred over add() in ingesters that may be re-run on existing data.
        SAP equivalent: MODIFY instead of INSERT.
        """
        return self.add(texts=texts, metadatas=metadatas, ids=ids)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """
        Semantic search against the collection.

        Parameters
        ----------
        query_text : str
            Natural-language question.
        n_results : int
            Maximum number of results to return.
        where : dict, optional
            ChromaDB metadata filter, e.g. ``{"source": {"$eq": "forum"}}``.

        Returns
        -------
        list[dict]
            Each dict has keys: ``text``, ``metadata``, ``distance``.
            Empty list when the collection is empty.
        """
        total = self._collection.count()
        if total == 0:
            return []

        query_embedding = self._model.encode([query_text], show_progress_bar=False).tolist()

        kwargs: dict = {
            "query_embeddings": query_embedding,
            "n_results": min(n_results, total),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        results = []
        for doc, meta, dist in zip(
            raw["documents"][0],
            raw["metadatas"][0],
            raw["distances"][0],
        ):
            results.append({"text": doc, "metadata": meta, "distance": dist})

        return results

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Total chunks currently stored."""
        return self._collection.count()

    def stats(self) -> dict:
        """
        Return total count plus a breakdown by the ``source`` metadata field.

        Example
        -------
        ::

            {"total": 42, "by_source": {"forum": 40, "docs": 2}}
        """
        total = self._collection.count()
        if total == 0:
            return {"total": 0, "by_source": {}}

        all_items = self._collection.get(include=["metadatas"])
        by_source: dict[str, int] = {}
        for meta in all_items["metadatas"]:
            src = meta.get("source", "unknown")
            by_source[src] = by_source.get(src, 0) + 1

        return {"total": total, "by_source": by_source}

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Delete the collection and recreate it empty."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

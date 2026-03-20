"""
Email Vector Store

Chunks, embeds, and indexes email content using ChromaDB + sentence-transformers.
Each user gets an isolated ChromaDB collection at CHROMA_PERSIST_DIR/{user_id}/.

Chunking strategy:
  - Split on double-newlines (paragraphs), then re-split paragraphs > 500 chars
    at sentence boundaries with 50-char overlap.
  - Prepend "Subject: {subject} | From: {sender} |" to each chunk so
    semantic search retrieves subject-level context even for body chunks.

Metadata stored per chunk: email_id, subject, sender, date.
"""
import logging
import re
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500       # characters
CHUNK_OVERLAP = 50
CONTEXT_PREFIX_MAX = 120  # max chars of subject+sender prepended to each chunk


def _split_into_chunks(text: str) -> list[str]:
    """Split text into overlapping ~CHUNK_SIZE-char chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []

    for para in paragraphs:
        if len(para) <= CHUNK_SIZE:
            chunks.append(para)
        else:
            # Split long paragraphs at sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 1 <= CHUNK_SIZE:
                    current = (current + " " + sent).strip()
                else:
                    if current:
                        chunks.append(current)
                    # Start new chunk with overlap from end of previous
                    overlap = current[-CHUNK_OVERLAP:] if len(current) > CHUNK_OVERLAP else current
                    current = (overlap + " " + sent).strip()
            if current:
                chunks.append(current)

    return chunks or [text[:CHUNK_SIZE]]


class EmailVectorStore:
    """Per-user ChromaDB collection for email chunks."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self._client = chromadb.PersistentClient(
            path=f"{settings.CHROMA_PERSIST_DIR}/{user_id}"
        )
        self._collection = self._client.get_or_create_collection(
            name="emails",
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = SentenceTransformer(settings.EMBEDDING_MODEL)

    def ingest_emails(self, emails: list[dict]) -> int:
        """
        Chunk, embed, and upsert a list of email dicts.
        Each email dict: {email_id, subject, sender, date, body}

        Returns: number of new chunks added.
        """
        ids, documents, metadatas = [], [], []

        for email in emails:
            email_id = email.get("email_id", "")
            subject  = email.get("subject", "")
            sender   = email.get("sender", "")
            date     = email.get("date", "")
            body     = email.get("body", "") or email.get("snippet", "")

            if not body:
                continue

            prefix = f"Subject: {subject[:80]} | From: {sender[:40]} | "
            chunks = _split_into_chunks(body)

            for i, chunk in enumerate(chunks):
                chunk_id = f"{email_id}_chunk_{i}"
                document = (prefix + chunk)[:CHUNK_SIZE + CONTEXT_PREFIX_MAX]
                ids.append(chunk_id)
                documents.append(document)
                metadatas.append({
                    "email_id": email_id,
                    "subject":  subject[:200],
                    "sender":   sender[:100],
                    "date":     date[:50],
                })

        if not ids:
            return 0

        # Compute embeddings
        embeddings = self._embedder.encode(documents, show_progress_bar=False).tolist()

        # Upsert (idempotent — safe to re-index same email)
        self._collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info(f"Ingested {len(ids)} chunks for user {self.user_id}")
        return len(ids)

    def search(
        self,
        query: str,
        top_k: int = 10,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """
        Semantic search over indexed emails.

        Returns list of dicts:
          {chunk_text, email_id, subject, sender, date, relevance_score}
        Sorted by relevance (best first).
        """
        if self._collection.count() == 0:
            return []

        query_embedding = self._embedder.encode([query], show_progress_bar=False)[0].tolist()

        kwargs = dict(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append({
                "chunk_text":      doc,
                "email_id":        meta.get("email_id", ""),
                "subject":         meta.get("subject", ""),
                "sender":          meta.get("sender", ""),
                "date":            meta.get("date", ""),
                "relevance_score": round(1 - dist, 4),  # cosine: 1=identical, 0=unrelated
            })

        return chunks

    def get_indexed_email_ids(self) -> set[str]:
        """Return set of email_ids that have at least one chunk indexed."""
        if self._collection.count() == 0:
            return set()
        # Fetch all metadata (ChromaDB paginates, but for <10k emails this is fine)
        result = self._collection.get(include=["metadatas"])
        return {m["email_id"] for m in result.get("metadatas", [])}

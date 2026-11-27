# Purpose of this file is to store and query document chunk vectors in ChromaDB
"""Step 4 of the knowledge-base pipeline: store vectors and search them.

ChromaDB keeps the chunk vectors on disk. Then always pass our own embeddings
(from embeddings.py) so Chroma never falls back to its default model.

Access control: ``query`` takes the set of document ids the user may read and
asks Chroma to search ONLY those documents, so restricted chunks never even
enter the candidate list.
"""

from pathlib import Path

import chromadb
from chromadb.config import Settings

from app.knowledge_base.preprocessing import Chunk

COLLECTION_NAME = "aegis_chunks"
BATCH_SIZE = 256


class VectorStore:
    def __init__(self, path: Path | str, collection_name: str = COLLECTION_NAME):
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(
            path=str(path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self._open()

    def _open(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        """Delete everything and start with an empty collection."""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:  # collection did not exist yet
            pass
        self.collection = self._open()

    def count(self) -> int:
        return self.collection.count()

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Store chunks with their vectors. Metadata values must be plain strings or numbers."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start : start + BATCH_SIZE]
            self.collection.upsert(
                ids=[c.chunk_id for c in batch],
                embeddings=embeddings[start : start + BATCH_SIZE],
                documents=[c.index_text for c in batch],
                metadatas=[
                    {
                        "doc_id": c.doc_id,
                        "doc_title": c.doc_title,
                        "version": c.version,
                        "page": c.page,
                        "section": c.section or "",
                        "status": c.status,
                    }
                    for c in batch
                ],
            )

    def query(
        self,
        query_embedding: list[float],
        n_results: int,
        allowed_doc_ids: set[str],
    ) -> list[tuple[str, float]]:
        """Return ``(chunk_id, similarity)`` pairs, best first, from allowed documents only."""
        total = self.count()
        if not allowed_doc_ids or total == 0:
            return []
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, total),
            where={"doc_id": {"$in": sorted(allowed_doc_ids)}},
            include=["distances"],
        )
        ids = result["ids"][0]
        distances = result["distances"][0]
        return [
            (chunk_id, 1.0 - dist) for chunk_id, dist in zip(ids, distances)
        ]  # cosine distance -> similarity

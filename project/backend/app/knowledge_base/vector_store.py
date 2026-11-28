# Purpose of this file is to store and query document chunk vectors in ChromaDB
"""Step 4 of the knowledge-base pipeline: store vectors and search them.

ChromaDB keeps the chunk vectors on disk. Then always pass our own embeddings
(from embeddings.py) so Chroma never falls back to its default model.

Access control: ``query`` takes the set of document ids the user may read and
asks Chroma to search ONLY those documents, so restricted chunks never even
enter the candidate list.
"""

import json
import math
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
except (ImportError, OSError):
    chromadb = None
    Settings = None

from app.knowledge_base.preprocessing import Chunk

COLLECTION_NAME = "aegis_chunks"
BATCH_SIZE = 256


class VectorStore:
    def __init__(self, path: Path | str, collection_name: str = COLLECTION_NAME):
        self.collection_name = collection_name
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.fallback_path = self.path / f"{collection_name}.json"
        if chromadb is None:
            self.client = None
            self.collection = None
        else:
            self.client = chromadb.PersistentClient(
                path=str(path),
                settings=Settings(anonymized_telemetry=False),
            )
            self.collection = self._open()

    def _open(self):
        if self.client is None:
            return None
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        """Delete everything and start with an empty collection."""
        if self.client is None:
            self.fallback_path.unlink(missing_ok=True)
            return
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:  # collection did not exist yet
            pass
        self.collection = self._open()

    def count(self) -> int:
        if self.collection is None:
            return len(self._fallback_records())
        return self.collection.count()

    def _fallback_records(self) -> list[dict]:
        if not self.fallback_path.exists():
            return []
        return json.loads(self.fallback_path.read_text(encoding="utf-8"))

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Store chunks with their vectors. Metadata values must be plain strings or numbers."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if self.collection is None:
            records = [
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "embedding": embedding,
                }
                for chunk, embedding in zip(chunks, embeddings)
            ]
            self.fallback_path.write_text(json.dumps(records), encoding="utf-8")
            return
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
        if self.collection is None:
            query_norm = math.sqrt(sum(value * value for value in query_embedding)) or 1.0
            matches = []
            for record in self._fallback_records():
                if record["doc_id"] not in allowed_doc_ids:
                    continue
                vector = record["embedding"]
                vector_norm = math.sqrt(sum(value * value for value in vector)) or 1.0
                similarity = sum(
                    left * right for left, right in zip(query_embedding, vector)
                ) / (query_norm * vector_norm)
                matches.append((record["chunk_id"], similarity))
            matches.sort(key=lambda item: item[1], reverse=True)
            return matches[:n_results]
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

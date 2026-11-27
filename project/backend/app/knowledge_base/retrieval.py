# Purpose of this file is to run hybrid (vector + BM25) search, apply role-based filtering and prefer the latest document version
"""Step 5 of the knowledge-base pipeline: find evidence for a claim.

How one search works
--------------------
1. AUTHORISE   Work out which documents the user's role may read. Everything
               below only ever looks at those documents.
2. DENSE       Embedding search (finds passages with the same MEANING).
3. KEYWORD     BM25 search (finds passages with the same WORDS and NUMBERS,
               such as "14" or "5 business days").
4. FUSE        Reciprocal Rank Fusion merges the two rankings.
5. TOP-K       The best few chunks (by relevance) are kept.
6. VERSION     Chunks from superseded documents stay in the list, because the
               verifier needs to see that an old FAQ disagrees. They are tagged
               "superseded" and their score is reduced, so current documents
               are listed first.
"""

import logging
import re
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.knowledge_base.embeddings import EmbedderProtocol, get_embedder
from app.knowledge_base.ingestion import DocumentMeta, iter_pages, load_manifest
from app.knowledge_base.preprocessing import (
    Chunk,
    build_chunks,
    load_chunks,
    save_chunks,
)
from app.knowledge_base.vector_store import VectorStore
from app.schemas.verification import EvidenceChunk

logger = logging.getLogger(__name__)

# Default locations (backend/data/...)
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
DOCS_DIR = DATA_DIR / "sample_documents"
MANIFEST_PATH = DOCS_DIR / "manifest.json"
CHUNKS_PATH = DATA_DIR / "processed" / "chunks.json"
CHROMA_PATH = DATA_DIR / "processed" / "chroma"

# Tuning knobs
DENSE_K = 20  # candidates taken from vector search
SPARSE_K = 20  # candidates taken from BM25
FINAL_K = 5  # evidence chunks returned per claim
RRF_K = 60  # standard Reciprocal Rank Fusion constant
SUPERSEDED_WEIGHT = 0.5  # score multiplier (applied AFTER the top-k cut) for chunks of superseded documents

_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|\w+")


def tokenize(text: str) -> list[str]:
    """Lowercase words and numbers. Numbers are kept on purpose: "14" must match "14"."""
    return _TOKEN_RE.findall(text.lower())


def reciprocal_rank_fusion(
    rankings: list[list[str]], k: int = RRF_K
) -> dict[str, float]:
    """Merge several ranked lists of ids. A chunk ranked high in either list scores well."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


class HybridRetriever:
    def __init__(
        self,
        chunks: list[Chunk],
        manifest: list[DocumentMeta],
        store: VectorStore,
        embedder: EmbedderProtocol,
        *,
        dense_k: int = DENSE_K,
        sparse_k: int = SPARSE_K,
        final_k: int = FINAL_K,
        superseded_weight: float = SUPERSEDED_WEIGHT,
    ):
        if not chunks:
            raise ValueError(
                "No chunks to search. Build the index first: python scripts/build_index.py"
            )
        self.chunks = chunks
        self.by_id = {c.chunk_id: c for c in chunks}
        self.docs = {d.doc_id: d for d in manifest}
        self.store = store
        self.embedder = embedder
        self.dense_k = dense_k
        self.sparse_k = sparse_k
        self.final_k = final_k
        self.superseded_weight = superseded_weight
        # BM25 has no persistence, so it is rebuilt from the chunk list at start-up.
        self.bm25 = BM25Okapi([tokenize(c.index_text) for c in chunks])

    # Access control
    def allowed_doc_ids(self, role: str | None) -> set[str]:
        """Ids of the documents this role may read. Unknown role -> empty set (default deny)."""
        return {doc_id for doc_id, doc in self.docs.items() if doc.is_allowed(role)}

    # Search
    def search(
        self, query: str, role: str | None, k: int | None = None
    ) -> list[EvidenceChunk]:
        return self.search_many([query], role, k)[0]

    def search_many(
        self, queries: list[str], role: str | None, k: int | None = None
    ) -> list[list[EvidenceChunk]]:
        """Search once per query. All queries are embedded together in one batch."""
        allowed = self.allowed_doc_ids(role)
        if not queries:
            return []
        if not allowed:
            logger.info(
                "Role %r may not read any document; returning no evidence.", role
            )
            return [[] for _ in queries]
        vectors = self.embedder.embed_queries(queries)
        return [
            self._search_one(q, v, allowed, k or self.final_k)
            for q, v in zip(queries, vectors)
        ]

    def _search_one(
        self, query: str, vector: list[float], allowed: set[str], k: int
    ) -> list[EvidenceChunk]:
        dense_ids = [
            chunk_id for chunk_id, _ in self.store.query(vector, self.dense_k, allowed)
        ]
        sparse_ids = self._bm25_ranking(query, allowed)
        fused = reciprocal_rank_fusion([dense_ids, sparse_ids])

        # Choose the top-k by RELEVANCE first. If the version penalty were applied before the cut,
        # a relevant but superseded chunk could be pushed out and the verifier would never see
        # that an old document disagrees.
        results: list[EvidenceChunk] = []
        for chunk_id, score in sorted(
            fused.items(), key=lambda item: item[1], reverse=True
        ):
            chunk = self.by_id.get(chunk_id)
            if (
                chunk is None or chunk.doc_id not in allowed
            ):  # second, independent access check
                continue
            if chunk.status == "superseded":
                score *= (
                    self.superseded_weight
                )  # then prefer current versions in the ordering
            results.append(
                EvidenceChunk(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    doc_title=chunk.doc_title,
                    version=chunk.version,
                    page=chunk.page,
                    section=chunk.section,
                    status=chunk.status,
                    effective_date=chunk.effective_date,
                    text=chunk.text,
                    score=round(score, 6),
                )
            )
            if len(results) == k:
                break
        results.sort(key=lambda e: e.score, reverse=True)
        return results

    def _bm25_ranking(self, query: str, allowed: set[str]) -> list[str]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        candidates = [
            (scores[i], chunk.chunk_id)
            for i, chunk in enumerate(self.chunks)
            if chunk.doc_id in allowed and scores[i] > 0
        ]
        candidates.sort(reverse=True)
        return [chunk_id for _, chunk_id in candidates[: self.sparse_k]]


# Building and loading the index
def build_index(
    docs_dir: Path | str = DOCS_DIR,
    manifest_path: Path | str = MANIFEST_PATH,
    chunks_path: Path | str = CHUNKS_PATH,
    store_path: Path | str = CHROMA_PATH,
    embedder: EmbedderProtocol | None = None,
) -> int:
    """Run the whole offline pipeline: PDFs -> chunks -> embeddings -> ChromaDB. Returns the chunk count."""
    embedder = embedder or get_embedder()
    manifest = load_manifest(manifest_path)
    chunks = build_chunks(iter_pages(manifest, docs_dir))
    if not chunks:
        raise ValueError(
            "No text could be extracted from the documents in the manifest."
        )
    save_chunks(chunks, chunks_path)

    store = VectorStore(store_path)
    store.reset()
    store.add_chunks(chunks, embedder.embed_passages([c.index_text for c in chunks]))
    logger.info("Indexed %d chunks from %d documents.", len(chunks), len(manifest))
    return len(chunks)


def load_retriever(
    manifest_path: Path | str = MANIFEST_PATH,
    chunks_path: Path | str = CHUNKS_PATH,
    store_path: Path | str = CHROMA_PATH,
    embedder: EmbedderProtocol | None = None,
    **options,
) -> HybridRetriever:
    """Open an already built index."""
    return HybridRetriever(
        chunks=load_chunks(chunks_path),
        manifest=load_manifest(manifest_path),
        store=VectorStore(store_path),
        embedder=embedder or get_embedder(),
        **options,
    )


@lru_cache(maxsize=1)
def get_retriever() -> HybridRetriever:
    """Shared retriever for the running application. Builds the index on first use if needed."""
    chunks_ready = CHUNKS_PATH.exists()
    store_count = VectorStore(CHROMA_PATH).count()
    if (
        not chunks_ready
        or store_count == 0
        or store_count != len(load_chunks(CHUNKS_PATH))
    ):
        logger.info("Index missing or out of date. Building it now.")
        build_index()
    return load_retriever()

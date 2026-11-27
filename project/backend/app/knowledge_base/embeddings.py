# Purpose of this file is to convert text chunks and claims into embedding vectors using sentence-transformers
"""Step 3 of the knowledge-base pipeline: text -> vectors.

An embedding turns a sentence into a list of numbers so that sentences with a
similar MEANING end up close together. Chunks and claims are embedded with the
same model, so "closest vector" means "most related passage".

The model is downloaded from Hugging Face the first time it is used and cached
afterwards. Change it with EMBEDDING_MODEL in .env.
"""

import os
from functools import lru_cache
from typing import Protocol

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# bge models work best when SEARCH QUERIES (not passages) start with this instruction.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbedderProtocol(Protocol):
    """Anything with these two methods can be used (the tests use a fake)."""

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class Embedder:
    """Sentence Transformers wrapper. The model is loaded once, on first use."""

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 32):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import (
                SentenceTransformer,
            )  # heavy import, so done lazily

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,  # unit length, so cosine similarity is a dot product
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks."""
        return self._encode(texts)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed claims used as search queries (batched in one call)."""
        if "bge" in self.model_name.lower():
            texts = [BGE_QUERY_PREFIX + t for t in texts]
        return self._encode(texts)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Shared embedder so the model is loaded only once per process."""
    return Embedder()

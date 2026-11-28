# Purpose of this file is to convert text chunks and claims into embedding vectors using sentence-transformers
"""Step 3 of the knowledge-base pipeline: text -> vectors.

An embedding turns a sentence into a list of numbers so that sentences with a
similar MEANING end up close together. Chunks and claims are embedded with the
same model, so "closest vector" means "most related passage".

The model is downloaded from Hugging Face the first time it is used and cached
afterwards. Change it with EMBEDDING_MODEL in .env.
"""

import hashlib
import logging
import math
import os
import re
from functools import lru_cache
from typing import Protocol

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
logger = logging.getLogger(__name__)

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
            texts = [BGE_QUERY_PREFIX + text for text in texts]
        return self._encode(texts)


class HashingEmbedder:
    """Pure-Python retrieval fallback for systems that block ML native DLLs."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _encode_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in re.findall(r"\d+(?:[.,]\d+)*|\w+", text.lower()):
            bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]


class ResilientEmbedder:
    """Prefer semantic embeddings and permanently fall back after a load failure."""

    def __init__(self, primary: Embedder | None = None, fallback=None):
        self.primary = primary or Embedder()
        self.fallback = fallback or HashingEmbedder()
        self._native_unavailable = False

    def _embed(self, method: str, texts: list[str]) -> list[list[float]]:
        if not self._native_unavailable:
            try:
                return getattr(self.primary, method)(texts)
            except (ImportError, OSError) as error:
                self._native_unavailable = True
                logger.warning(
                    "Semantic embedder unavailable; using pure-Python hashing fallback: %s",
                    error,
                )
        return getattr(self.fallback, method)(texts)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._embed("embed_passages", texts)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._embed("embed_queries", texts)


@lru_cache(maxsize=1)
def get_embedder() -> EmbedderProtocol:
    """Shared embedder so the model is loaded only once per process."""
    if os.getenv("EMBEDDING_BACKEND", "").strip().lower() == "hashing":
        return HashingEmbedder()
    return ResilientEmbedder()

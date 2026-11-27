# Purpose of this file is to provide a fake LLM and a fake embedder so tests and the offline demo run without API keys or model downloads
"""Test doubles. Never used in the real pipeline.

* ``ScriptedLLM``: returns prepared responses instead of calling an API.
* ``HashingEmbedder``: turns text into a deterministic bag-of-words vector.
  It is not semantic, but texts that share words get similar vectors, which is
  enough to test the retrieval pipeline end to end.
"""

import hashlib
import math
import re
from typing import Any


class ScriptedLLM:
    """Callable with the same signature as ``core.llm_client.call_structured``.

    ``responses`` is a list of model instances (returned) or exceptions (raised),
    used in order. The last item repeats if the agent calls more often.
    """

    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, system: str, user: str, schema: type) -> Any:
        self.calls.append({"system": system, "user": user, "schema": schema})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        item = self.responses[index]
        if isinstance(item, Exception):
            raise item
        return item


class HashingEmbedder:
    """Deterministic fake embedder with the same interface as ``Embedder``."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in re.findall(r"\d+(?:[.,]\d+)*|\w+", text.lower()):
            bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

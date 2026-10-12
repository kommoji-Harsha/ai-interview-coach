"""Embedding services for text chunk vectorization."""

import hashlib
import math
from abc import ABC, abstractmethod


class EmbeddingService(ABC):
    """Abstract interface for text embedding generation."""

    dimension: int = 1536

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate vector embedding for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for a list of texts."""
        ...


class DeterministicEmbeddingService(EmbeddingService):
    """Generates deterministic, normalized float embeddings for testing and offline environments.

    Projects token n-grams into a 1536-dimensional unit sphere using feature hashing.
    Text with overlapping keywords and concepts has high cosine similarity.
    """

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def _embed_sync(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        if not text:
            return vec

        # Tokenize words and character 3-grams
        tokens = [t.lower() for t in text.split() if t]
        ngrams: list[str] = list(tokens)
        for token in tokens:
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    ngrams.append(token[i : i + 3])

        for tok in ngrams:
            # Hash to index and sign (+1 or -1)
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if ((h >> 32) & 1) == 0 else -1.0
            vec[idx] += sign

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]

        return vec

    async def embed_text(self, text: str) -> list[float]:
        return self._embed_sync(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_sync(t) for t in texts]


def get_embedding_service(dimension: int = 1536) -> EmbeddingService:
    """Return configured embedding service (defaults to deterministic unit-vector provider)."""
    return DeterministicEmbeddingService(dimension=dimension)

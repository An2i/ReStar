import hashlib
import math

from backend.config import TOKEN_PATTERN


try:
    from langchain_core.embeddings import Embeddings as LangChainEmbeddings
except ImportError:  # pragma: no cover - fallback keeps the API usable before deps install.
    class LangChainEmbeddings:  # type: ignore[no-redef]
        pass


class LocalHashEmbeddings(LangChainEmbeddings):
    """A deterministic local embedding model compatible with LangChain vector stores."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = TOKEN_PATTERN.findall(text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            index = int(digest[:12], 16) % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

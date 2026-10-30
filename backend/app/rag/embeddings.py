"""Embedding providers with a provider abstraction.

- ``openai`` provider calls any OpenAI-compatible /embeddings endpoint.
- ``mock`` provider computes deterministic hashed bag-of-ngrams embeddings
  locally. It is keyword-semantic (not deep-semantic) and exists so the whole
  RAG pipeline is runnable and testable offline with zero API keys. Swap the
  provider via env vars for production quality.
"""

import hashlib
import math
import re

import httpx

from app.config.settings import get_settings

settings = get_settings()

_TOKEN = re.compile(r"[a-z0-9\u0600-\u06FF]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class LocalHashEmbedding:
    """Deterministic TF-weighted hashing embedding with unigrams + bigrams."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _index(self, token: str) -> int:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "little") % self.dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        toks = _tokens(text)
        grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        if not grams:
            return vec
        for gram in grams:
            vec[self._index(gram)] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 8) for v in vec]


class OpenAICompatibleEmbedding:
    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        base = (settings.embedding_base_url or settings.llm_base_url).rstrip("/")
        key = settings.embedding_api_key or settings.llm_api_key
        resp = httpx.post(
            f"{base}/embeddings",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": settings.embedding_model, "input": text[:8000]},
            timeout=30,
        )
        resp.raise_for_status()
        return [round(v, 8) for v in resp.json()["data"][0]["embedding"]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        base = (settings.embedding_base_url or settings.llm_base_url).rstrip("/")
        key = settings.embedding_api_key or settings.llm_api_key
        resp = httpx.post(
            f"{base}/embeddings",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": settings.embedding_model, "input": [t[:8000] for t in texts]},
            timeout=60,
        )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [[round(v, 8) for v in d["embedding"]] for d in data]


class EmbeddingService:
    def __init__(self):
        use_openai = (
            settings.embedding_provider == "openai"
            and bool(settings.embedding_api_key or settings.llm_api_key)
        )
        self._remote = OpenAICompatibleEmbedding(settings.embedding_dim) if use_openai else None
        self._local = LocalHashEmbedding(settings.embedding_dim)

    @property
    def provider_name(self) -> str:
        return "openai-compatible" if self._remote else "local-hash"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._remote:
            try:
                if hasattr(self._remote, "embed_batch"):
                    return self._remote.embed_batch(texts)
                return [self._remote.embed(t) for t in texts]
            except Exception:
                # Degrade gracefully so ingestion never hard-fails offline.
                pass
        return [self._local.embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


embedding_service = EmbeddingService()

"""Embedding providers (ADR-0012).

* :class:`FastEmbedEmbedder` - local ONNX ``bge-small-en-v1.5`` (384-d, L2-normalised). Nothing
  leaves the machine at ingestion time.
* :class:`HashEmbedder` - deterministic, model-free vectors for unit/integration tests.
* :class:`CachedEmbedder` - wraps any embedder with a persistent cache keyed by
  ``sha256(model_id + input)`` so re-seeding, re-chunking with unchanged text, and CI runs only
  embed *new* text.

Embedding is CPU-bound; callers run it in a worker thread (``asyncio.to_thread``).
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

Vector = npt.NDArray[np.float32]


class EmbedderUnavailableError(RuntimeError):
    """The embedding model cannot be loaded or failed; ingestion degrades to lexical-only."""


class Embedder(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_passages(self, texts: Sequence[str]) -> list[Vector]: ...

    def embed_query(self, text: str) -> Vector: ...


def embed_key(model_id: str, text: str) -> str:
    return hashlib.sha256(f"{model_id}\x00{text}".encode()).hexdigest()


class FastEmbedEmbedder:
    """Lazily loads the ONNX model once per process (thread-safe)."""

    def __init__(
        self,
        model_id: str,
        model_name: str,
        dimensions: int,
        cache_dir: Path,
        threads: int | None = None,
        batch_size: int = 64,
    ) -> None:
        self._model_id = model_id
        self._model_name = model_name
        self._dimensions = dimensions
        self._cache_dir = cache_dir
        self._threads = threads
        self._batch_size = batch_size
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                try:
                    from fastembed import TextEmbedding

                    self._cache_dir.mkdir(parents=True, exist_ok=True)
                    self._model = TextEmbedding(
                        self._model_name, cache_dir=str(self._cache_dir), threads=self._threads
                    )
                except Exception as exc:
                    raise EmbedderUnavailableError(f"cannot load {self._model_name}") from exc
            return self._model

    @property
    def tokenizer(self) -> Any:
        """The model's own ``tokenizers.Tokenizer`` (window sizes match what the model sees)."""
        return self._load().model.tokenizer

    def embed_passages(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        try:
            vectors = list(self._load().passage_embed(list(texts), batch_size=self._batch_size))
        except EmbedderUnavailableError:
            raise
        except Exception as exc:
            raise EmbedderUnavailableError("embedding failed") from exc
        return [np.asarray(v, dtype=np.float32) for v in vectors]

    def embed_query(self, text: str) -> Vector:
        try:
            (vector,) = list(self._load().query_embed([text]))
        except EmbedderUnavailableError:
            raise
        except Exception as exc:
            raise EmbedderUnavailableError("query embedding failed") from exc
        return np.asarray(vector, dtype=np.float32)


class HashEmbedder:
    """Deterministic pseudo-embeddings: same text, same unit vector. Tests only."""

    def __init__(self, model_id: str = "hash-test", dimensions: int = 384) -> None:
        self._model_id = model_id
        self._dimensions = dimensions
        self.calls = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _vector(self, text: str) -> Vector:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        vector = np.random.default_rng(seed).standard_normal(self._dimensions).astype(np.float32)
        norm = float(np.linalg.norm(vector))
        return (vector / norm).astype(np.float32)

    def embed_passages(self, texts: Sequence[str]) -> list[Vector]:
        self.calls += len(texts)
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> Vector:
        return self._vector(text)


class FailingEmbedder(HashEmbedder):
    """Simulates an unavailable embedding provider (degradation tests)."""

    def embed_passages(self, texts: Sequence[str]) -> list[Vector]:
        raise EmbedderUnavailableError("simulated outage")

    def embed_query(self, text: str) -> Vector:
        raise EmbedderUnavailableError("simulated outage")


class EmbeddingCache:
    """Persistent (model, input) -> vector cache in one SQLite file per model."""

    def __init__(self, directory: Path, model_id: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._path = directory / f"{model_id}.sqlite3"
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS v (k TEXT PRIMARY KEY, b BLOB NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=30)

    def get_many(self, keys: Sequence[str]) -> dict[str, Vector]:
        found: dict[str, Vector] = {}
        with self._lock, self._connect() as conn:
            for start in range(0, len(keys), 500):
                chunk = list(keys[start : start + 500])
                marks = ",".join("?" * len(chunk))
                for key, blob in conn.execute(f"SELECT k, b FROM v WHERE k IN ({marks})", chunk):  # noqa: S608 - placeholders only
                    found[key] = np.frombuffer(blob, dtype=np.float32).copy()
        return found

    def put_many(self, items: dict[str, Vector]) -> None:
        with self._lock, self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO v (k, b) VALUES (?, ?)",
                [(k, np.asarray(v, dtype=np.float32).tobytes()) for k, v in items.items()],
            )


class CachedEmbedder:
    """Embeds only cache misses; reports how many vectors were reused."""

    def __init__(self, inner: Embedder, cache: EmbeddingCache) -> None:
        self._inner = inner
        self._cache = cache
        self.last_hits = 0
        self.last_misses = 0

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    def embed_passages(self, texts: Sequence[str]) -> list[Vector]:
        keys = [embed_key(self.model_id, t) for t in texts]
        cached = self._cache.get_many(keys)
        missing = [i for i, k in enumerate(keys) if k not in cached]
        self.last_hits = len(texts) - len(missing)
        self.last_misses = len(missing)
        if missing:
            fresh = self._inner.embed_passages([texts[i] for i in missing])
            new = {keys[i]: v for i, v in zip(missing, fresh, strict=True)}
            self._cache.put_many(new)
            cached.update(new)
        return [cached[k] for k in keys]

    def embed_query(self, text: str) -> Vector:
        return self._inner.embed_query(text)

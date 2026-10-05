"""Cross-encoder rerankers behind one interface (ADR-0005).

The default is fastembed's ONNX ``Xenova/ms-marco-MiniLM-L-6-v2``, run locally on CPU. A
cross-encoder reads the query and the passage *together*, so it can order the top of a
candidate pool better than either retriever's independent scores. Scores are raw logits:
comparable within one query, not calibrated across queries.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol


class RerankerUnavailableError(RuntimeError):
    """The reranker could not load or failed; callers keep the fused order."""


class Reranker(Protocol):
    @property
    def model_id(self) -> str: ...

    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class FastEmbedCrossEncoder:
    """Lazily loads the ONNX cross-encoder once per process (thread-safe)."""

    def __init__(
        self, model_name: str, cache_dir: Path, threads: int | None = None, batch_size: int = 64
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._threads = threads
        self._batch_size = batch_size
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return self._model_name

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                try:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    self._cache_dir.mkdir(parents=True, exist_ok=True)
                    self._model = TextCrossEncoder(
                        self._model_name, cache_dir=str(self._cache_dir), threads=self._threads
                    )
                except Exception as exc:
                    raise RerankerUnavailableError(f"cannot load {self._model_name}") from exc
            return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        try:
            model = self._load()
            return [
                float(s) for s in model.rerank(query, list(passages), batch_size=self._batch_size)
            ]
        except RerankerUnavailableError:
            raise
        except Exception as exc:
            raise RerankerUnavailableError("reranking failed") from exc


class FailingReranker:
    """Test double: always fails (reranker outage)."""

    model_id = "failing-reranker"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        raise RerankerUnavailableError("simulated outage")


class SlowReranker:
    """Test double: sleeps past any reasonable timeout, then scores by passage length."""

    model_id = "slow-reranker"

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        time.sleep(self.seconds)
        return [float(len(p)) for p in passages]


class KeywordReranker:
    """Deterministic test double: score = how many query words the passage contains."""

    model_id = "keyword-reranker"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        words = {w for w in query.lower().split() if len(w) > 2}
        return [float(sum(1 for w in words if w in p.lower())) for p in passages]

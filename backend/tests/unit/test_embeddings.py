from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from marketsignal.providers.embeddings import (
    CachedEmbedder,
    EmbedderUnavailableError,
    EmbeddingCache,
    FailingEmbedder,
    HashEmbedder,
    embed_key,
)


def test_hash_embedder_is_deterministic_and_normalised() -> None:
    embedder = HashEmbedder(dimensions=16)
    a, b = embedder.embed_passages(["fit", "fit"])
    assert np.allclose(a, b)
    assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-5
    assert not np.allclose(a, embedder.embed_query("delivery"))


def test_cache_embeds_only_misses_and_survives_restart(tmp_path: Path) -> None:
    inner = HashEmbedder(dimensions=8)
    first = CachedEmbedder(inner, EmbeddingCache(tmp_path, inner.model_id))
    vectors = first.embed_passages(["a", "b", "a"])
    assert (first.last_hits, first.last_misses, inner.calls) == (0, 3, 3)
    # A new process (new cache object, same file) reuses everything.
    second = CachedEmbedder(inner, EmbeddingCache(tmp_path, inner.model_id))
    again = second.embed_passages(["a", "b", "c"])
    assert (second.last_hits, second.last_misses) == (2, 1)
    assert np.allclose(vectors[0], again[0])
    assert inner.calls == 4


def test_cache_keys_are_namespaced_by_model() -> None:
    assert embed_key("m1", "text") != embed_key("m2", "text")


def test_failing_embedder_raises_unavailable() -> None:
    with pytest.raises(EmbedderUnavailableError):
        FailingEmbedder().embed_passages(["x"])

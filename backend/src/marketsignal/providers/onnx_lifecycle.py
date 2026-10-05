"""Release ONNX Runtime sessions before interpreter teardown.

If an onnxruntime ``InferenceSession`` is still alive when Python tears down its modules, its
destructor can run after onnxruntime's own static objects are gone; on macOS this aborts the
process ("libc++abi: ... recursive_mutex lock failed") *after* all work succeeded - an exit
code 134 that would fail CI steps and test runs at random. Every provider that loads a model
registers itself here; an ``atexit`` hook (which runs before module teardown) drops all model
references and collects them while the runtime is still intact.
"""

from __future__ import annotations

import atexit
import gc
import weakref
from typing import Protocol


class Releasable(Protocol):
    def release(self) -> None: ...


_holders: weakref.WeakSet[Releasable] = weakref.WeakSet()


def register(holder: Releasable) -> None:
    _holders.add(holder)


def release_all() -> None:
    for holder in list(_holders):
        holder.release()
    gc.collect()


atexit.register(release_all)

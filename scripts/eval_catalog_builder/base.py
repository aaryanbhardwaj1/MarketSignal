"""Shared metric, provenance and row helpers used by every section mixin."""

from __future__ import annotations

import re
from typing import Any

from .common import Sources, resolve, slug


class BuilderBase:
    def __init__(self, src: Sources) -> None:
        self.src = src

    # metric helpers -----------------------------------------------------------------------
    def metric(
        self,
        mid: str,
        label: str,
        path: str,
        pointer: str,
        unit: str,
        *,
        ci: tuple[str, str] | None = None,
        n: int | str | None = None,
        k: int | str | None = None,
    ) -> dict[str, Any]:
        doc = self.src.json(path)
        value = resolve(doc, pointer)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int | float)):
            raise TypeError(f"{path}#{pointer} is not a number: {value!r}")
        out: dict[str, Any] = {"id": mid, "label": label, "value": value, "unit": unit}
        if ci is not None:
            out["ci_low"] = resolve(doc, ci[0])
            out["ci_high"] = resolve(doc, ci[1])
        for key, spec in (("n", n), ("k", k)):
            if spec is not None:
                out[key] = resolve(doc, spec) if isinstance(spec, str) else spec
        out["source"] = {"kind": "json", "path": path, "pointer": pointer}
        return out

    def est(
        self, mid: str, label: str, path: str, base: str, unit: str = "ratio", **kw: Any
    ) -> dict[str, Any]:
        """Metric from an ``{estimate, low, high}`` block."""
        return self.metric(
            mid, label, path, base + "/estimate", unit, ci=(base + "/low", base + "/high"), **kw
        )

    def md(self, path: str, heading: str) -> dict[str, Any]:
        text = self.src.text(path)
        if not re.search(r"^#+ " + re.escape(heading) + r"\s*$", text, re.M):
            raise KeyError(f"heading {heading!r} not found in {path}")
        return {"kind": "report_md", "path": path, "anchor": slug(heading)}

    # provenance -----------------------------------------------------------------------------
    def provenance(
        self,
        path: str,
        *,
        split: str | None,
        dataset: dict[str, Any],
        model_key: str | None = "model",
    ) -> dict[str, Any]:
        run = self.src.json(path)["run"]
        return {
            "path": path,
            "git": run.get("git"),
            "at": run.get("at"),
            "model": run.get(model_key) if model_key else None,
            "split": split,
            "config_hash": run.get("config_hash") or run.get("retrieval_config_hash"),
            "dataset": dataset,
        }

    def file_dataset(self, name: str, rel: str) -> dict[str, Any]:
        doc = self.src.json(rel)
        return {"name": name, "version": doc.get("dataset_version"), "sha256": self.src.sha(rel)}

    def row_index(self, rows: list[dict[str, Any]], run: str, arm: str) -> int:
        for i, row in enumerate(rows):
            if row["run"] == run and row["arm"] == arm:
                return i
        raise KeyError(f"no row for {run}/{arm}")

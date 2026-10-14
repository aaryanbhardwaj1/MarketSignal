"""Load and validate a ``marketsignal.ragas-samples`` file (format_version 1).

Anything that does not match the contract is refused with a :class:`SamplesError`; nothing is
coerced or guessed.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLES_FORMAT = "marketsignal.ragas-samples"
SAMPLES_FORMAT_VERSION = 1

_ID_TEXT_PAIRS = (
    ("retrieved_context_ids", "retrieved_contexts"),
    ("cited_context_ids", "cited_contexts"),
    ("reference_context_ids", "reference_contexts"),
)


class SamplesError(ValueError):
    """The samples file is missing, unreadable or violates the samples contract."""


@dataclass(frozen=True)
class Sample:
    item_id: str
    category: str
    configuration: str
    user_input: str
    response: str
    reference: str | None
    retrieved_context_ids: tuple[str, ...]
    cited_context_ids: tuple[str, ...]
    reference_context_ids: tuple[str, ...]
    retrieved_contexts: tuple[str, ...]
    cited_contexts: tuple[str, ...]
    reference_contexts: tuple[str, ...]
    excluded: str | None


@dataclass(frozen=True)
class ExcludedEntry:
    item_id: str
    configuration: str
    reason: str


@dataclass(frozen=True)
class SamplesFile:
    path: Path
    sha256: str
    run_id: str
    run_title: str | None
    configurations: tuple[str, ...]
    samples: tuple[Sample, ...]
    excluded: tuple[ExcludedEntry, ...]

    def scorable(self, configuration: str) -> tuple[Sample, ...]:
        """Samples of ``configuration`` that are not marked excluded."""
        return tuple(
            s for s in self.samples if s.configuration == configuration and s.excluded is None
        )

    def excluded_count(self, configuration: str) -> int:
        listed = sum(1 for e in self.excluded if e.configuration == configuration)
        flagged = sum(
            1 for s in self.samples if s.configuration == configuration and s.excluded is not None
        )
        return listed + flagged


def _require_str(obj: dict[str, Any], key: str, where: str, *, allow_empty: bool = False) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SamplesError(f"{where}.{key} must be a non-empty string")
    return value


def _optional_str(obj: dict[str, Any], key: str, where: str) -> str | None:
    if key not in obj:
        raise SamplesError(f"{where}.{key} is required (use null when absent)")
    value = obj[key]
    if value is not None and not isinstance(value, str):
        raise SamplesError(f"{where}.{key} must be a string or null")
    return value


def _str_list(obj: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = obj.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SamplesError(f"{where}.{key} must be a list of strings")
    return tuple(value)


def _require_dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SamplesError(f"{where} must be an object")
    return value


def _parse_sample(raw: Any, index: int, configurations: tuple[str, ...]) -> Sample:
    where = f"samples[{index}]"
    obj = _require_dict(raw, where)
    lists = {key: _str_list(obj, key, where) for pair in _ID_TEXT_PAIRS for key in pair}
    for ids_key, texts_key in _ID_TEXT_PAIRS:
        if len(lists[ids_key]) != len(lists[texts_key]):
            raise SamplesError(
                f"{where}: {ids_key} has {len(lists[ids_key])} entries but {texts_key} has "
                f"{len(lists[texts_key])}"
            )
    configuration = _require_str(obj, "configuration", where)
    if configuration not in configurations:
        raise SamplesError(f"{where}.configuration {configuration!r} is not in run.configurations")
    return Sample(
        item_id=_require_str(obj, "item_id", where),
        category=_require_str(obj, "category", where),
        configuration=configuration,
        user_input=_require_str(obj, "user_input", where),
        response=_require_str(obj, "response", where, allow_empty=True),
        reference=_optional_str(obj, "reference", where),
        retrieved_context_ids=lists["retrieved_context_ids"],
        cited_context_ids=lists["cited_context_ids"],
        reference_context_ids=lists["reference_context_ids"],
        retrieved_contexts=lists["retrieved_contexts"],
        cited_contexts=lists["cited_contexts"],
        reference_contexts=lists["reference_contexts"],
        excluded=_optional_str(obj, "excluded", where),
    )


def _parse_excluded(raw: Any, configurations: tuple[str, ...]) -> tuple[ExcludedEntry, ...]:
    if not isinstance(raw, list):
        raise SamplesError("excluded must be a list")
    entries = []
    for index, item in enumerate(raw):
        where = f"excluded[{index}]"
        obj = _require_dict(item, where)
        configuration = _require_str(obj, "configuration", where)
        if configuration not in configurations:
            raise SamplesError(f"{where}.configuration {configuration!r} is not declared")
        entries.append(
            ExcludedEntry(
                item_id=_require_str(obj, "item_id", where),
                configuration=configuration,
                reason=_require_str(obj, "reason", where),
            )
        )
    return tuple(entries)


def _read_json(path: Path) -> tuple[Any, str]:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise SamplesError(f"samples file not found: {path}") from exc
    try:
        return json.loads(data), hashlib.sha256(data).hexdigest()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SamplesError(f"samples file is not valid JSON: {exc}") from exc


def load_samples(path: Path) -> SamplesFile:
    raw, sha256 = _read_json(path)
    payload = _require_dict(raw, "samples file")
    if payload.get("format") != SAMPLES_FORMAT:
        raise SamplesError(f"format must be {SAMPLES_FORMAT!r}")
    version = payload.get("format_version")
    if type(version) is not int or version != SAMPLES_FORMAT_VERSION:
        raise SamplesError(f"format_version must be {SAMPLES_FORMAT_VERSION}")
    run = _require_dict(payload.get("run"), "run")
    run_id = _require_str(run, "id", "run")
    configurations = _str_list(run, "configurations", "run")
    if not configurations or len(set(configurations)) != len(configurations):
        raise SamplesError("run.configurations must be a non-empty list of unique names")
    if not isinstance(payload.get("samples"), list):
        raise SamplesError("samples must be a list")
    samples = tuple(
        _parse_sample(item, i, configurations) for i, item in enumerate(payload["samples"])
    )
    seen: set[tuple[str, str]] = set()
    for sample in samples:
        key = (sample.item_id, sample.configuration)
        if key in seen:
            raise SamplesError(f"duplicate sample {key[0]!r} for configuration {key[1]!r}")
        seen.add(key)
    title = run.get("title")
    return SamplesFile(
        path=path,
        sha256=sha256,
        run_id=run_id,
        run_title=title if isinstance(title, str) else None,
        configurations=configurations,
        samples=samples,
        excluded=_parse_excluded(payload.get("excluded", []), configurations),
    )

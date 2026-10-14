import json
from pathlib import Path
from typing import Any

import pytest

from ms_ragas_runner.samples import SamplesError, load_samples
from tests.conftest import write_payload


def test_loads_valid_file(samples_file: Path) -> None:
    loaded = load_samples(samples_file)
    assert loaded.run_id == "unit-run"
    assert loaded.configurations == ("standard",)
    assert [s.item_id for s in loaded.samples] == ["U-001", "U-002"]
    assert loaded.samples[0].retrieved_context_ids == ("h:a", "h:b", "h:c", "h:d")
    assert loaded.samples[0].reference is None
    assert len(loaded.sha256) == 64
    assert loaded.excluded_count("standard") == 1


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.update(format="something-else"), "format"),
        (lambda p: p.update(format_version=2), "format_version"),
        (lambda p: p.update(format_version=True), "format_version"),
        (lambda p: p.pop("samples"), "samples"),
        (lambda p: p["run"].pop("id"), "run.id"),
        (lambda p: p["run"].update(configurations=[]), "configurations"),
        (lambda p: p["samples"][0].pop("user_input"), "user_input"),
        (lambda p: p["samples"][0].update(response=None), "response"),
        (lambda p: p["samples"][0]["retrieved_contexts"].pop(), "retrieved"),
        (lambda p: p["samples"][0]["cited_context_ids"].append("h:z"), "cited"),
        (lambda p: p["samples"][0]["reference_contexts"].append("extra"), "reference"),
        (lambda p: p["samples"][0].update(retrieved_context_ids="h:a"), "retrieved_context_ids"),
        (lambda p: p["samples"][0].update(retrieved_context_ids=[1, 2, 3, 4]), "retrieved"),
        (lambda p: p["samples"][0].update(configuration="research"), "configuration"),
        (lambda p: p["samples"].append(dict(p["samples"][0])), "duplicate"),
        (lambda p: p["samples"][0].update(reference=7), "reference"),
        (lambda p: p["excluded"][0].pop("reason"), "reason"),
    ],
)
def test_refuses_invalid_payloads(
    tmp_path: Path, samples_payload: dict[str, Any], mutate: Any, message: str
) -> None:
    mutate(samples_payload)
    path = write_payload(tmp_path, samples_payload)
    with pytest.raises(SamplesError, match=message):
        load_samples(path)


def test_refuses_non_object_and_bad_json(tmp_path: Path) -> None:
    listed = tmp_path / "list.json"
    listed.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(SamplesError, match="object"):
        load_samples(listed)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(SamplesError, match="JSON"):
        load_samples(broken)
    with pytest.raises(SamplesError, match="not found"):
        load_samples(tmp_path / "missing.json")


def test_sample_level_exclusion_is_counted(tmp_path: Path, samples_payload: dict[str, Any]) -> None:
    samples_payload["samples"][1]["excluded"] = "unresolvable_handle"
    loaded = load_samples(write_payload(tmp_path, samples_payload))
    assert [s.item_id for s in loaded.scorable("standard")] == ["U-001"]
    assert loaded.excluded_count("standard") == 2

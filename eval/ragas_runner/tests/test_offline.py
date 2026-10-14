import json
import math
from pathlib import Path
from typing import Any

import pytest

from ms_ragas_runner.offline import run_offline, score_sample_offline
from ms_ragas_runner.registry import LLM_KEYS, OFFLINE_KEYS
from ms_ragas_runner.results import OutputExistsError, summarize
from ms_ragas_runner.samples import load_samples
from tests.conftest import write_payload


def test_id_based_scores_match_hand_computation(samples_file: Path) -> None:
    first, second = load_samples(samples_file).samples
    s1 = score_sample_offline(first)
    assert s1["id_context_recall_pack"] == pytest.approx(0.5)  # gold {a,e}, pack has a
    assert s1["id_context_precision_pack"] == pytest.approx(0.25)  # 1 of 4 pack ids is gold
    assert s1["id_context_recall_cited"] == pytest.approx(0.5)
    assert s1["id_context_precision_cited"] == pytest.approx(1.0)
    s2 = score_sample_offline(second)
    assert s2["id_context_recall_pack"] == pytest.approx(1.0)
    assert s2["id_context_precision_pack"] == pytest.approx(1.0)
    assert s2["id_context_recall_cited"] == pytest.approx(0.0)  # nothing cited
    assert s2["id_context_precision_cited"] is None  # undefined, never invented


def test_text_scores_are_ragas_values(samples_file: Path) -> None:
    first, second = load_samples(samples_file).samples
    s2 = score_sample_offline(second)
    assert s2["nonllm_context_recall_pack"] == pytest.approx(1.0)  # identical passage
    assert s2["nonllm_context_precision_pack"] == pytest.approx(1.0)
    s1 = score_sample_offline(first)
    for key in ("nonllm_context_recall_pack", "nonllm_context_precision_pack"):
        value = s1[key]
        assert value is not None
        assert 0.0 <= value <= 1.0
    assert set(s1) == set(OFFLINE_KEYS)


def test_empty_pack_text_metrics_are_null_not_zero(
    tmp_path: Path, samples_payload: dict[str, Any]
) -> None:
    sample = samples_payload["samples"][1]
    sample["retrieved_context_ids"] = []
    sample["retrieved_contexts"] = []
    loaded = load_samples(write_payload(tmp_path, samples_payload))
    scores = score_sample_offline(loaded.samples[1])
    assert scores["id_context_recall_pack"] == pytest.approx(0.0)
    assert scores["id_context_precision_pack"] is None
    assert scores["nonllm_context_recall_pack"] is None


def test_summarize_statistics_and_histogram() -> None:
    summary = summarize([0.5, 1.0, None])
    assert summary["mean"] == pytest.approx(0.75)
    assert summary["median"] == pytest.approx(0.75)
    assert summary["p25"] == pytest.approx(0.625)
    assert summary["p75"] == pytest.approx(0.875)
    assert (summary["min"], summary["max"], summary["n"], summary["n_nan"]) == (0.5, 1.0, 2, 1)
    hist = summary["histogram"]
    assert len(hist) == 10
    assert hist[0]["lo"] == 0.0
    assert hist[-1]["hi"] == 1.0
    assert [b["n"] for b in hist] == [0, 0, 0, 0, 0, 1, 0, 0, 0, 1]
    empty = summarize([None])
    assert empty["n"] == 0
    assert empty["n_nan"] == 1
    assert empty["mean"] is None


def test_run_offline_writes_results_and_report(tmp_path: Path, samples_file: Path) -> None:
    out = tmp_path / "out"
    results = run_offline([samples_file], out)
    on_disk = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert on_disk == results
    assert on_disk["format"] == "marketsignal.ragas-results"
    assert on_disk["format_version"] == 1
    assert on_disk["telemetry_disabled"] is True
    assert on_disk["ragas_version"] == "0.4.3"
    assert on_disk["inputs"][0]["run_id"] == "unit-run"
    assert len(on_disk["inputs"][0]["sha256"]) == 64
    assert not Path(on_disk["inputs"][0]["path"]).is_absolute()
    assert {m["key"] for m in on_disk["metrics"]} == set(OFFLINE_KEYS) | set(LLM_KEYS)

    (run,) = on_disk["runs"]
    assert (run["run_id"], run["configuration"]) == ("unit-run", "standard")
    assert (run["n_samples"], run["n_excluded"]) == (2, 1)
    recall = run["summary"]["id_context_recall_pack"]
    assert recall["status"] == "computed"
    assert recall["mean"] == pytest.approx(0.75)
    assert run["summary"]["id_context_precision_cited"]["n_nan"] == 1
    for key in LLM_KEYS:
        entry = run["summary"][key]
        assert entry["status"] == "not_run"
        assert entry["not_run_reason"] in {"no_reference_answers", "model_credits_unavailable"}
        assert not any(k in entry for k in ("mean", "median", "n", "histogram"))
    assert run["summary"]["faithfulness"]["not_run_reason"] == "model_credits_unavailable"
    assert run["summary"]["factual_correctness"]["not_run_reason"] == "no_reference_answers"
    item = run["items"][1]
    assert item["item_id"] == "U-002"
    assert item["scores"]["id_context_precision_cited"] is None
    assert set(item["scores"]) == set(OFFLINE_KEYS)

    raw = (out / "results.json").read_text(encoding="utf-8")
    assert "NaN" not in raw
    report = (out / "report.md").read_text(encoding="utf-8")
    for needle in ("What was measured", "Not measured", "not objective truth", "unit-run"):
        assert needle in report


def test_refuses_existing_out_dir(tmp_path: Path, samples_file: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(OutputExistsError):
        run_offline([samples_file], out)
    assert not (out / "results.json").exists()


def test_multiple_files_and_duplicate_runs(tmp_path: Path, samples_payload: dict[str, Any]) -> None:
    research = json.loads(json.dumps(samples_payload))
    research["run"]["configurations"] = ["research"]
    for s in research["samples"]:
        s["configuration"] = "research"
    research["excluded"] = []
    first = write_payload(tmp_path, samples_payload, "a.json")
    second = write_payload(tmp_path, research, "b.json")
    results = run_offline([first, second], tmp_path / "out")
    assert [(r["configuration"], r["n_excluded"]) for r in results["runs"]] == [
        ("standard", 1),
        ("research", 0),
    ]
    with pytest.raises(ValueError, match="more than once"):
        run_offline([first, first], tmp_path / "out2")
    assert not (tmp_path / "out2").exists()


def test_nan_never_reaches_json() -> None:
    from ms_ragas_runner.results import to_json_safe

    assert to_json_safe({"a": [math.nan, 1.0], "b": math.inf}) == {"a": [None, 1.0], "b": None}


def test_display_path_is_never_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ms_ragas_runner.results import display_path

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "eval" / "runner").mkdir(parents=True)
    target = repo / "eval" / "reports" / "x.json"
    monkeypatch.chdir(repo / "eval" / "runner")
    assert display_path(Path("../reports/x.json")) == "eval/reports/x.json"
    assert display_path(target) == "eval/reports/x.json"
    outside = tmp_path / "elsewhere" / "y.json"
    assert display_path(outside) == "y.json"

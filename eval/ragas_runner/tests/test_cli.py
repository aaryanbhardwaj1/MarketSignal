import json
from pathlib import Path
from typing import Any

import pytest

from ms_ragas_runner import cli, llm


def test_offline_command_writes_artifacts(tmp_path: Path, samples_file: Path) -> None:
    out = tmp_path / "out"
    assert cli.main(["offline", "--samples", str(samples_file), "--out", str(out)]) == 0
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert results["mode"] == "offline"
    assert (out / "report.md").is_file()
    # a second run into the same directory is refused
    assert cli.main(["offline", "--samples", str(samples_file), "--out", str(out)]) == 2


def test_offline_command_rejects_bad_samples(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "nope"}), encoding="utf-8")
    assert cli.main(["offline", "--samples", str(bad), "--out", str(tmp_path / "o")]) == 2
    assert not (tmp_path / "o").exists()


def test_llm_command_refuses_without_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    samples_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("client constructed")

    monkeypatch.setattr(llm, "AsyncAnthropic", _raise)
    monkeypatch.delenv("MS_LIVE_LLM", raising=False)
    code = cli.main(["llm", "--samples", str(samples_file), "--out", str(tmp_path / "o")])
    assert code == 2
    assert "refused" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()

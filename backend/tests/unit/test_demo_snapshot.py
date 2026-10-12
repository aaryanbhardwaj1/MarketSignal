"""Demo snapshot scripts: logical-key remapping, drift guards and the safety denylist, over fake
rows (no database)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import _demo_common as common
import demo_export
import demo_import
import demo_reset

H = "NORTHSTAR/INTERVIEWS@v1:S14.Q1"
CHILD = "def99e1c-1f1e-4b15-9268-b15c65b4c712"
OTHER = "53b1a46d-376e-4c6b-a11b-76ab53f7a1ae"


def _citation(**extra: Any) -> dict[str, Any]:
    return {
        "handle": H,
        "char_start": 0,
        "char_end": 236,
        "anchor_child_id": CHILD,
        "parent_content_hash": "abc",
        **extra,
    }


def _trace_stages() -> dict[str, Any]:
    return {
        "dense": [{"handle": H, "span": [0, 1053], "child_id": OTHER, "rank": 1}],
        "final": [{"handle": H, "anchor": {"lane": "dense", "span": [0, 1053], "child_id": OTHER}}],
    }


def test_parse_handle_matches_the_sql_split() -> None:
    assert common.parse_handle(H) == common.HandleKey("NORTHSTAR", "INTERVIEWS", 1)
    assert common.parse_handle("NORTHSTAR/SURVEY-2026@v12") == common.HandleKey(
        "NORTHSTAR", "SURVEY-2026", 12
    )
    assert common.parse_handle("R1") is None
    assert common.parse_handle("NORTHSTAR/CODE@vX:P1") is None


def test_child_ref_round_trips_and_rejects_garbage() -> None:
    ref = common.child_ref(H, 5, 40)
    assert ref == f"child:{H}#5-40"
    assert common.parse_child_ref(ref) == (H, 5, 40)
    for bad in ("child:no-span", f"child:{H}#5", f"{H}#1-2", f"child:{H}#a-b"):
        with pytest.raises(common.SnapshotError):
            common.parse_child_ref(bad)


def test_logicalize_replaces_citation_and_trace_child_ids() -> None:
    row = {"citations": [_citation(), {"kind": "result", "result_id": str(uuid.uuid4())}]}
    row["stages"] = _trace_stages()
    logical = common.logicalize_children(row)
    assert logical["citations"][0]["anchor_child_id"] == f"child:{H}#0-236"
    assert logical["stages"]["dense"][0]["child_id"] == f"child:{H}#0-1053"
    assert logical["stages"]["final"][0]["anchor"]["child_id"] == f"child:{H}#0-1053"
    assert logical["citations"][1] == row["citations"][1]  # result citations untouched
    assert row["citations"][0]["anchor_child_id"] == CHILD  # input not mutated
    refs = common.child_refs_in(logical)
    assert refs == {f"child:{H}#0-236", f"child:{H}#0-1053"}
    lookup = {f"child:{H}#0-236": CHILD, f"child:{H}#0-1053": OTHER}
    assert common.resolve_children(logical, lookup) == row


def test_null_anchor_is_kept_and_unkeyable_anchor_fails() -> None:
    assert common.logicalize_children(_citation(anchor_child_id=None))["anchor_child_id"] is None
    with pytest.raises(common.SnapshotError):
        common.logicalize_children({"anchor_child_id": CHILD})  # no handle / span


def test_resolve_children_aborts_on_missing_child() -> None:
    with pytest.raises(common.SnapshotError, match="corpus drift"):
        common.resolve_children({"anchor_child_id": f"child:{H}#0-9"}, {})


def test_denylist_base_patterns_and_local_file(tmp_path: Path) -> None:
    clean = {"content": "Gen Z buyers [E1]", "usage": {"input_tokens": 10}}
    assert common.denylist_hits(clean, common.BASE_DENY_PATTERNS) == []
    dirty = {
        "a": "/Users/someone/x",
        "b": ["see sk-ant-123"],
        "c": {"api_key": 1},
        "d": "postgresql+psycopg://u:p@h/db",
        "e": "ANTHROPIC_API_KEY",
    }
    hits = common.denylist_hits(dirty, common.BASE_DENY_PATTERNS)
    assert hits == ["$.a", "$.b[0]", "$.c.api_key", "$.d", "$.e"]
    local = tmp_path / "deny.local"
    local.write_text("# comment\n\nzorblax\n", encoding="utf-8")
    patterns = common.load_denylist(local)
    assert common.denylist_hits({"x": "the ZORBLAX deck"}, patterns) == ["$.x"]
    assert common.load_denylist(tmp_path / "absent") == common.BASE_DENY_PATTERNS


def test_foreign_uuid_scan_and_own_ids() -> None:
    run, conv, msg = (str(uuid.uuid4()) for _ in range(3))
    snapshot = {
        "conversations": [
            {
                "conversation": {"id": conv},
                "messages": [{"id": msg, "content": f"[[result:{run}]]"}],
                "runs": [
                    {
                        "query_run": {"id": run},
                        **{t: [] for t in demo_import._RUN_TABLES},
                    }
                ],
            }
        ]
    }
    own = demo_export.own_ids(snapshot)
    assert own == {run, conv, msg}
    assert common.foreign_uuids(snapshot, own) == []
    snapshot["conversations"][0]["messages"][0]["x"] = CHILD
    assert common.foreign_uuids(snapshot, own) == ["$.conversations[0].messages[0].x"]


def test_render_is_deterministic() -> None:
    a = demo_export.render({"b": 1, "a": {"z": "é", "y": [2, 1]}})
    b = demo_export.render({"a": {"y": [2, 1], "z": "é"}, "b": 1})
    assert a == b
    assert a.endswith("\n")
    assert "é" in a


def _snapshot() -> dict[str, Any]:
    run = {
        "id": "r1",
        "pack_handles": [H],
        "cited_handles": [H, "NORTHSTAR/GENZ-TRENDS@v1:P1"],
    }
    result = {"id": "x1", "dataset_ref": {"source_code": "SURVEY-2026", "version": 1}}
    return {
        "format": common.SNAPSHOT_FORMAT,
        "format_version": common.SNAPSHOT_FORMAT_VERSION,
        "workspace": "NORTHSTAR",
        "conversations": [
            {
                "conversation": {"id": "c1"},
                "messages": [{"id": "m1", "citations": [_citation()]}],
                "runs": [
                    {
                        "query_run": run,
                        "run_events": [{"seq": 1}],
                        "tool_runs": [],
                        "retrieval_traces": [],
                        "verification_attempts": [],
                        "analytics_results": [result],
                    }
                ],
            }
        ],
    }


def test_rows_by_table_flattens_in_fk_order() -> None:
    rows = demo_import.rows_by_table(_snapshot())
    assert list(rows) == list(demo_import.INSERT_ORDER)
    assert [len(rows[t]) for t in demo_import.INSERT_ORDER] == [1, 1, 1, 1, 0, 0, 0, 1]


def test_version_guard_accepts_ready_and_superseded_only() -> None:
    rows = demo_import.rows_by_table(_snapshot())
    wanted = demo_import.version_keys(rows)
    assert wanted == {("INTERVIEWS", 1), ("GENZ-TRENDS", 1), ("SURVEY-2026", 1)}
    live = {
        ("INTERVIEWS", 1): "ready",
        ("GENZ-TRENDS", 1): "superseded",
        ("SURVEY-2026", 1): "ready",
    }
    assert demo_import.drifted_versions(wanted, live) == []
    purged = {**live, ("GENZ-TRENDS", 1): "purged"}
    assert demo_import.drifted_versions(wanted, purged) == ["GENZ-TRENDS@v1:purged"]
    missing = {k: v for k, v in live.items() if k[0] != "SURVEY-2026"}
    assert demo_import.drifted_versions(wanted, missing) == ["SURVEY-2026@v1:missing"]


def test_parent_hash_guard() -> None:
    cites = demo_import.evidence_citations(demo_import.rows_by_table(_snapshot()))
    assert len(cites) == 1
    assert demo_import.hash_mismatches(cites, {H: "abc"}) == []
    assert demo_import.hash_mismatches(cites, {H: "changed"}) == [H]
    assert demo_import.hash_mismatches(cites, {}) == [H]


def test_format_guard() -> None:
    demo_import.validate_format(_snapshot())
    with pytest.raises(common.SnapshotError):
        demo_import.validate_format({**_snapshot(), "format_version": 99})
    with pytest.raises(common.SnapshotError):
        demo_import.validate_format({"format": "other"})


def test_reset_only_ever_targets_test_codes() -> None:
    found = ["NORTHSTAR", "T06E0A37CDC", "T9771AE8367", "Tabcdef1234", "T06E0A37CDC0"]
    assert demo_reset.select_targets(found, None) == ["T06E0A37CDC", "T9771AE8367"]
    assert demo_reset.select_targets(found, ["T9771AE8367"]) == ["T9771AE8367"]
    with pytest.raises(ValueError, match="non-test"):
        demo_reset.select_targets(found, ["NORTHSTAR"])
    assert common.is_test_workspace_code("T0123456789")
    assert not common.is_test_workspace_code("SOUTHPEAK")


def test_featured_list_is_six_distinct_conversations() -> None:
    assert len(set(common.FEATURED_NORTHSTAR)) == 6
    assert all(common.UUID_RE.fullmatch(c) for c in common.FEATURED_NORTHSTAR)

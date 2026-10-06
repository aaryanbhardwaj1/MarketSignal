"""Markdown report of an analytics evaluation run (results.json -> report.md)."""

from __future__ import annotations

from typing import Any


def _fmt(value: Any) -> str:
    if isinstance(value, dict) and "rate" in value:
        if value.get("n") is not None:
            shown = "n/a" if value["rate"] is None else f"{value['rate']:.3f}"
            return f"{value['k']}/{value['n']} ({shown})"
        return "n/a" if value["rate"] is None else f"{value['rate']:.3f}"
    if isinstance(value, float):
        return f"{value:.3f}"
    return "n/a" if value is None else str(value)


def _table(rows: list[tuple[str, Any]]) -> list[str]:
    return ["| metric | value |", "|---|---|", *(f"| {k} | {_fmt(v)} |" for k, v in rows)]


def _section(title: str, data: dict[str, Any]) -> list[str]:
    rows = [(k, v) for k, v in data.items() if not isinstance(v, list | dict) or "rate" in v]
    return [f"## {title}", "", *_table(rows), ""]


def render(result: dict[str, Any]) -> str:
    s = result["summary"]
    run = result.get("run") or {}
    lines = [
        "# Analytics evaluation (analytics-v0)",
        "",
        f"- git `{run.get('git')}` at {run.get('at')}; model `{run.get('model')}`; "
        f"mode `{run.get('mode')}`; split `{run.get('split')}`; items {s['n']}; "
        f"elapsed {result.get('elapsed_s')} s",
        "",
        "## Hard gates",
        "",
        "| gate | value | pass |",
        "|---|---|---|",
        *(
            f"| {name} | {g['value']} | {'PASS' if g['pass'] else 'FAIL'} |"
            for name, g in s["hard_gates"].items()
        ),
        "",
    ]
    routing = s["routing"]
    lines += _section("Routing", routing)
    lines += [f"Confusion (gold->decided): {routing['confusion']}", ""]
    analytics = dict(s["analytics"])
    micro = analytics.pop("exact_result_accuracy_micro")
    lines += _section("Analytics correctness", {**analytics, "exact_result_accuracy_micro": micro})
    lines += _section("Generated answers", s["answer"])
    lines += _section("Mixed", s["mixed"])
    security = s["security"]
    lines += _section("Security", security)
    lines += [
        f"- cross-workspace leak items: {security['cross_workspace_leak_items'] or 'none'}",
        f"- canary leaks: {security['canary_leaks'] or 'none'}",
        f"- tool error codes on invalid/insufficient items: "
        f"{security['invalid_item_tool_errors'] or 'none'}",
        "",
    ]
    perf = s["performance"]
    lines += ["## Performance", "", "| metric | n | p50 | p95 |", "|---|---|---|---|"]
    for key in ("analytics_tool_ms", "mixed_end_to_end_ms", "end_to_end_ms"):
        d = perf[key]
        lines.append(f"| {key} | {d['n']} | {_fmt(d['p50'])} | {_fmt(d['p95'])} |")
    lines += ["", *_table([(k, v) for k, v in perf.items() if not isinstance(v, dict)]), ""]
    lines += [
        "## Categories",
        "",
        "| category | n | behaviour pass | task type ok | exact-result acc | values stated |",
        "|---|---|---|---|---|---|",
        *(
            f"| {name} | {c['n']} | {c['behaviour_pass']} | {c['task_type_correct']} | "
            f"{_fmt(c['exact_result_accuracy_mean'])} | {_fmt(c['values_stated_rate_mean'])} |"
            for name, c in s["categories"].items()
        ),
        "",
        f"Termination states: {s['termination_states']}",
        "",
    ]
    return "\n".join(lines)

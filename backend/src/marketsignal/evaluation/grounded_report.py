"""Markdown rendering of a grounded-answer evaluation (results.json -> report.md) and of the
paired standard-vs-research comparison (results-*.json + compare.json -> report.md)."""

from __future__ import annotations

from typing import Any

MODES = ("standard", "research")


def render(result: dict[str, Any]) -> str:
    s = result["summary"]
    run = result.get("run", {})
    lines = [
        "# Grounded-answer evaluation",
        "",
        f"- Items: {s['n']} · mode {run.get('mode') or 'default'} · model `{run.get('model')}` "
        f"(effort {run.get('effort')}, thinking "
        f"{run.get('thinking')}) · git {run.get('git')} · {result['elapsed_s']} s",
        "",
        "## Hard gates",
        "",
        "| Gate | Value | Pass |",
        "|---|---|---|",
    ]
    for name, gate in s["hard_gates"].items():
        missing = f" (items: {', '.join(gate['missing'])})" if gate.get("missing") else ""
        verdict = "yes" if gate["pass"] else "**no**"
        lines.append(f"| {name} | {gate['value']}{missing} | {verdict} |")
    lines += [
        "",
        "## Behaviour by category",
        "",
        "Gold coverage and numeric correctness count LLM-generated answers only; evidence-only "
        "fallbacks are shown separately.",
        "",
        "| Category | n | answered | behaviour pass | gold coverage | numeric correct "
        "| fallback gold coverage | fallback numeric | evidence-only |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, c in s["categories"].items():
        lines.append(
            f"| {name} | {c['n']} | {c['answered']} | {c['behaviour_pass']} | "
            f"{c['gold_coverage_mean']} | {c['numeric_correct_mean']} | "
            f"{c['fallback_gold_coverage_mean']} | {c['fallback_numeric_correct_mean']} | "
            f"{c['evidence_only']} |"
        )
    lat = s["latency_ms"]
    lines += [
        "",
        f"- Over-refusal on answerable items: {s['over_refusal']['k']}/{s['over_refusal']['n']}",
        f"- Insufficient-evidence handled: {s['insufficient_correct']['k']}/"
        f"{s['insufficient_correct']['n']}",
        f"- Canary leaks: {s['canary_leaks'] or 'none'}",
        f"- Regenerations: {s['regenerations']}; termination states: {s['termination_states']}",
        f"- Latency: first token p50 {lat['first_token_p50']} / p95 {lat['first_token_p95']} ms; "
        f"total p50 {lat['total_p50']} / p95 {lat['total_p95']} ms",
        f"- Tokens (total): {s['usage_total']}; mean per model run: {s['usage_per_llm_run_mean']}",
        *_pipeline_lines(result.get("pipeline")),
        *_runs_lines(result.get("runs")),
        "",
        "## Stored-content contract re-check failures",
        "",
    ]
    if s["contract_recheck_failures"]:
        for f in s["contract_recheck_failures"]:
            lines.append(f"- {f['id']}: {f['problems']}")
    else:
        lines.append("- none")
    lines += ["", "## Items", ""]
    for item in result["items"]:
        c = item["checks"]
        lines.append(
            f"### {item['id']} ({item['category']}) - {item['termination_state']}"
            f"{' · flags ' + ', '.join(item['flags']) if item['flags'] else ''}"
        )
        lines.append("")
        lines.append(f"**Q:** {item['question']}")
        lines.append("")
        lines.append(
            f"checks: behaviour={c.get('pass_behaviour')} citations={c['citations']} "
            f"resolvable={c['resolvable']} in_pack={c['in_pack']} "
            f"answered={c.get('answered')} llm_called={c.get('llm_called')} "
            f"coverage={c.get('gold_coverage')} numeric={c.get('numeric_correct')} "
            f"fallback_coverage={c.get('fallback_gold_coverage')} "
            f"fallback_numeric={c.get('fallback_numeric_correct')}"
        )
        repairs = (item.get("verification") or {}).get("repairs") or []
        violations = (item.get("verification") or {}).get("numeric_violations") or []
        if repairs or violations:
            lines.append(f"repairs: {repairs} · numeric violations: {violations}")
        lines.append("")
        lines.append("```markdown")
        lines.append((item["content"] or "(no final)").strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"


def _pipeline_lines(pipeline: dict[str, Any] | None) -> list[str]:
    if not pipeline:
        return []
    lines = [
        "",
        "## Pipeline",
        "",
        "| Stage (ms) | n | p50 | p95 | max |",
        "|---|---|---|---|---|",
    ]
    for stage, d in pipeline["stage_latency_ms"].items():
        lines.append(f"| {stage} | {d['n']} | {d['p50']} | {d['p95']} | {d['max']} |")
    v = pipeline["verification"]
    cost = pipeline["cost_usd"]
    lines += [
        "",
        f"- Verification: {v}",
        f"- Approximate cost (USD, list prices {pipeline['prices_usd_per_mtok']}): {cost}",
    ]
    return lines


def _fmt(value: Any) -> str:
    if isinstance(value, dict) and "k" in value and "n" in value:
        return f"{value['k']}/{value['n']}"
    if isinstance(value, float):
        return f"{value:.4g}"
    return "-" if value is None else str(value)


def _effort_rows(runs: dict[str, Any]) -> list[tuple[str, str]]:
    lat = runs["latency_ms"]
    tok = runs["tokens_total"]
    unsupported = runs["unsupported_claim_rate"]
    rows = [
        ("model calls (total / mean)", "model_calls"),
        ("tool calls (total / mean)", "tool_calls"),
        ("tool failures (total / mean)", "tool_failures"),
        ("retrieval calls (total / mean)", "retrieval_calls"),
        ("agent steps (total / mean)", "steps"),
    ]
    out = [(label, f"{runs[k]['total']} / {_fmt(runs[k]['mean'])}") for label, k in rows]
    out += [
        (
            "tokens in / out / cache read / cache write",
            f"{tok['input']} / {tok['output']} / {tok['cache_read']} / {tok['cache_write']}",
        ),
        (
            "cost USD (total / per run)",
            f"{runs['cost_usd']['total']} / {runs['cost_usd']['per_run']}",
        ),
        (
            "first token ms p50 / p95",
            f"{_fmt(lat['first_token_p50'])} / {_fmt(lat['first_token_p95'])}",
        ),
        ("end-to-end ms p50 / p95", f"{_fmt(lat['total_p50'])} / {_fmt(lat['total_p95'])}"),
        ("research fallbacks", str(runs["research_fallbacks"])),
        ("regenerations", str(runs["regenerations"])),
        ("evidence-only fallbacks", str(runs["evidence_only"])),
        ("behaviour pass", _fmt(runs["behaviour_pass"])),
        ("gold coverage (cited, mean)", _fmt(runs["gold_coverage_mean"])),
        ("answer completeness (mean)", _fmt(runs["answer_completeness_mean"])),
        ("gold handle recall (pack, mean)", _fmt(runs["gold_handle_recall_mean"])),
        (
            "unsupported cited units",
            f"{unsupported['unsupported_units']}/{unsupported['cited_units']} "
            f"({_fmt(unsupported['rate'])})",
        ),
        ("conflict coverage", _fmt(runs["conflict_coverage"])),
        ("abstention correct", _fmt(runs["abstention_correct"])),
        ("routes decided", str(runs["routes_decided"])),
        ("agent stop reasons", str(runs["stop_reasons"] or "-")),
        ("termination states", str(runs["termination_states"])),
    ]
    if runs.get("router_agreement"):
        agree = runs["router_agreement"]
        out.append(("router agreement (auto)", f"{_fmt(agree)} {agree['confusion']}"))
    return out


def _runs_lines(runs: dict[str, Any] | None) -> list[str]:
    if not runs:
        return []
    lines = ["", "## Runs", "", "| Metric | Value |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in _effort_rows(runs)]
    return lines


def _failures(item: dict[str, Any]) -> list[str]:
    c = item["checks"]
    reasons = []
    if c.get("pass_behaviour") is False:
        reasons.append("behaviour")
    if c.get("contract_problems"):
        reasons.append(f"contract {c['contract_problems']}")
    if c.get("resolvable", 0) < c.get("citations", 0):
        reasons.append("unresolvable citation")
    if c.get("in_pack", 0) < c.get("citations", 0):
        reasons.append("citation not in pack")
    if c.get("foreign_citations") or c.get("southpeak_marker_leak"):
        reasons.append("cross-workspace leak")
    if c.get("unsupported_units"):
        reasons.append(f"unsupported numbers {c.get('unsupported_numbers')}")
    if not c.get("has_done", True):
        reasons.append("no done")
    return reasons


def _failure_lines(mode: str, items: list[dict[str, Any]]) -> list[str]:
    lines = ["", f"### {mode}", ""]
    failed = [(i, r) for i in items if (r := _failures(i))]
    if not failed:
        return [*lines, "- none"]
    for item, reasons in failed:
        m = item.get("metrics") or {}
        lines += [
            f"#### {item['id']} ({item['category']}) - {item['termination_state']}"
            f" · stop {m.get('stop_reason')} · flags {item.get('flags') or []}",
            "",
            f"**Q:** {item['question']}",
            "",
            f"failures: {'; '.join(reasons)}",
            "",
            "```markdown",
            (item["content"] or "(no final)").strip(),
            "```",
        ]
    return lines


def render_comparison(
    cmp: dict[str, Any], results: dict[str, dict[str, Any]], *, run: dict[str, Any]
) -> str:
    std, res = (results[m] for m in MODES)
    lines = [
        "# Grounded evaluation: standard vs research",
        "",
        f"- Paired items: {cmp['n_pairs']} (unpaired: {cmp['unpaired'] or 'none'}) · model "
        f"`{run.get('model')}` · git {run.get('git')} · split {run.get('split')} · "
        f"{std['elapsed_s']} s standard / {res['elapsed_s']} s research",
        f"- Deltas are {cmp['delta']}; 95% CIs are paired bootstrap "
        f"({cmp['bootstrap_samples']} resamples); rates also carry an exact McNemar p.",
        "",
        "## Hard gates",
        "",
        "| Gate | standard | research |",
        "|---|---|---|",
    ]
    for name, gate in std["summary"]["hard_gates"].items():
        other = res["summary"]["hard_gates"][name]
        cells = [
            f"{g['value']}{'' if g['pass'] else ' **FAIL**'}"
            + (f" ({', '.join(g['missing'])})" if g.get("missing") else "")
            for g in (gate, other)
        ]
        lines.append(f"| {name} | {cells[0]} | {cells[1]} |")
    lines += [
        "",
        "## Comparison",
        "",
        "| Metric | standard | research | research - standard (95% CI) | n pairs |",
        "|---|---|---|---|---|",
    ]
    for name, m in cmp["metrics"].items():
        ci = m.get("ci")
        delta = _fmt(m["delta_mean"]) + (f" [{_fmt(ci['low'])}, {_fmt(ci['high'])}]" if ci else "")
        if m.get("mcnemar"):
            delta += f" · McNemar p={_fmt(m['mcnemar']['p_value'])}"
        lines.append(
            f"| {name} | {_fmt(m['standard_mean'])} | {_fmt(m['research_mean'])} | {delta} "
            f"| {m['n_pairs']} |"
        )
    lines += [
        "",
        "## Cost, effort and termination",
        "",
        "| | standard | research |",
        "|---|---|---|",
    ]
    for (label, a), (_, b) in zip(
        _effort_rows(std["runs"]), _effort_rows(res["runs"]), strict=True
    ):
        lines.append(f"| {label} | {a} | {b} |")
    lines += ["", "## By category"]
    for name, c in cmp["categories"].items():
        lines += [
            "",
            f"### {name} (n={c['n']})",
            "",
            "| Metric | standard | research | Δ |",
            "|---|---|---|---|",
        ]
        for metric, m in c["metrics"].items():
            if m["n_pairs"]:
                lines.append(
                    f"| {metric} | {_fmt(m['standard_mean'])} | {_fmt(m['research_mean'])} "
                    f"| {_fmt(m['delta_mean'])} |"
                )
    lines += ["", "## Per-item failures"]
    for mode, result in zip(MODES, (std, res), strict=True):
        lines += _failure_lines(mode, result["items"])
    return "\n".join(lines) + "\n"

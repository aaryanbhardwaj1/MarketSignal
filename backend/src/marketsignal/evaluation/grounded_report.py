"""Markdown rendering of a grounded-answer evaluation (results.json -> report.md)."""

from __future__ import annotations

from typing import Any


def render(result: dict[str, Any]) -> str:
    s = result["summary"]
    run = result.get("run", {})
    lines = [
        "# Grounded-answer evaluation",
        "",
        f"- Items: {s['n']} · model `{run.get('model')}` (effort {run.get('effort')}, thinking "
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

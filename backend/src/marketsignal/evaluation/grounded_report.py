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
        lines.append(f"| {name} | {gate['value']} | {'yes' if gate['pass'] else '**no**'} |")
    lines += [
        "",
        "## Behaviour by category",
        "",
        "| Category | n | behaviour pass | gold coverage | numeric correct | evidence-only |",
        "|---|---|---|---|---|---|",
    ]
    for name, c in s["categories"].items():
        lines.append(
            f"| {name} | {c['n']} | {c['behaviour_pass']} | {c['gold_coverage_mean']} | "
            f"{c['numeric_correct_mean']} | {c['evidence_only']} |"
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
            f"coverage={c.get('gold_coverage')} numeric={c.get('numeric_correct')}"
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

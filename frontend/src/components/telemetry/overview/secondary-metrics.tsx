import type { ReactNode } from "react";
import type { Pct, StageKey, TelemetrySummaryWithOutcomes } from "@/lib/api/contracts";
import { Disclosure } from "@/components/ui/disclosure";
import { formatMs, formatNumber, formatPercent } from "@/lib/format";
import { sumValues } from "@/lib/telemetry-view";

interface Item {
  term: string;
  value: ReactNode;
  note?: string;
}

const pair = (p: Pct | undefined, fmt: (v: number | null) => string): string =>
  !p || p.n === 0 ? "Not recorded" : `${fmt(p.p50)} / ${fmt(p.p95)}`;

const STAGE_ITEMS: { key: StageKey; term: string }[] = [
  { key: "retrieval", term: "Retrieval p50 / p95" },
  { key: "agent", term: "Research steps p50 / p95" },
  { key: "synthesis", term: "Generation p50 / p95" },
  { key: "verification", term: "Verification p50 / p95" },
  { key: "first_token", term: "First token p50 / p95" },
];

function items(s: TelemetrySummaryWithOutcomes): Item[] {
  const total = s.runs.total;
  const failed = s.runs.by_status.failed ?? 0;
  const cancelled = sumValues(s.runs.by_status, ["cancelled", "interrupted"]);
  const errors = (s.errors ?? []).map((e) => `${e.error_class ?? "unclassified"} (${e.n})`).join(", ");
  const pack = s.evidence_pack;
  const num = (v: number | null) => formatNumber(v, 1);
  return [
    { term: "Failed runs", value: formatNumber(failed), note: errors || (failed ? "Error class not recorded" : undefined) },
    { term: "Cancelled or interrupted", value: formatNumber(cancelled) },
    { term: "Model calls", value: formatNumber(s.model_calls.total), note: `${formatNumber(s.model_calls.per_run_mean, 2)} per run${s.model_calls.n_runs_missing ? ` · not recorded for ${formatNumber(s.model_calls.n_runs_missing)} runs` : ""}` },
    { term: "Tool calls", value: formatNumber(s.tool_calls.total), note: `${formatNumber(s.tool_calls.per_run_mean, 2)} per run` },
    { term: "Tokens in / out", value: `${formatNumber(s.tokens.input)} / ${formatNumber(s.tokens.output)}`, note: `Cache read ${formatNumber(s.tokens.cache_read)} · cache write ${formatNumber(s.tokens.cache_write)}` },
    { term: "Evidence pack size p50 / p95", value: pair(pack?.size, num), note: "Passages handed to generation" },
    { term: "Cited passages p50 / p95", value: pair(pack?.cited, num), note: "Distinct passages the answer cites" },
    ...STAGE_ITEMS.map((st) => ({ term: st.term, value: pair(s.latency_ms.stages[st.key], formatMs), note: s.latency_ms.stages[st.key]?.n ? `${formatNumber(s.latency_ms.stages[st.key].n)} runs` : undefined })),
    { term: "Regeneration", value: formatPercent(s.rates.regeneration), note: "Answer rewritten after failing checks" },
    { term: "Planner fallback", value: formatPercent(s.rates.planner_fallback), note: "Research fell back to a standard search" },
    { term: "Degraded", value: formatPercent(s.rates.degraded), note: total ? `of ${formatNumber(total)} runs` : undefined },
    { term: "Test-harness runs", value: formatNumber(s.test_runs_excluded), note: "Excluded from these figures unless included above" },
  ];
}

/** Secondary figures as a compact definition grid (value under its term, note beneath). */
export function SecondaryMetrics({ summary }: { summary: TelemetrySummaryWithOutcomes }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
      {items(summary).map((it) => (
        <div key={it.term} className="min-w-0 border-t border-border pt-2">
          <dt className="text-xs text-muted">{it.term}</dt>
          <dd className="mt-0.5 text-md font-medium tabular-nums text-primary">{it.value}</dd>
          {it.note && <dd className="text-xs text-muted">{it.note}</dd>}
        </div>
      ))}
    </dl>
  );
}

const GLOSSARY: { term: string; meaning: string }[] = [
  { term: "p50 / p95", meaning: "Median and 95th percentile: half of runs are faster than p50, 95% faster than p95." },
  { term: "Run order", meaning: "Position of a run among those in the window, oldest first. Used as the x-axis because most runs were recorded within hours of each other." },
  { term: "Standard and Research", meaning: "Standard runs search once and answer; Research runs plan and call audited tools before answering." },
  { term: "Evidence pack", meaning: "The passages selected and budgeted for generation; cited passages are the ones the final answer references." },
  { term: "Verification fallback", meaning: "Citation checks failed, so a conservative evidence-only answer was shown instead." },
  { term: "Regeneration", meaning: "The first draft failed citation checks and was rewritten once." },
  { term: "Planner fallback", meaning: "Research planning was unavailable, so the run used a standard evidence search." },
  { term: "Degraded", meaning: "The run recorded at least one degradation flag (for example reduced search or no live model)." },
  { term: "Estimated cost", meaning: "Persisted token usage priced at list prices. An estimate, not a billed amount." },
  { term: "Test-harness runs", meaning: "Runs created by automated evaluation in test workspaces. Excluded by default." },
];

export function TelemetryGlossary() {
  return (
    <Disclosure summary="Metric glossary">
      <dl className="grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
        {GLOSSARY.map((g) => (
          <div key={g.term} className="min-w-0">
            <dt className="font-medium text-primary">{g.term}</dt>
            <dd className="text-secondary">{g.meaning}</dd>
          </div>
        ))}
      </dl>
    </Disclosure>
  );
}

import type { ReactNode } from "react";
import type { Pct, TelemetrySummary } from "@/lib/api/contracts";
import { BarList, type BarItem } from "@/components/ui/bar-list";
import { Callout } from "@/components/ui/callout";
import { Table, type Column } from "@/components/ui/table";
import { formatMs, formatNumber, formatPercent, formatUsd } from "@/lib/format";
import {
  degradationFlag,
  routeReason,
  verificationDisposition,
  verificationFailure,
  type Humanized,
} from "@/lib/labels";
import { glossaryTitle } from "@/lib/eval-view";
import { STAGE_ROWS, ofTotal, sumValues, toolStatusLabel } from "@/lib/telemetry-view";
import { NotRecorded, Panel, StatTile } from "./stat-tile";

type Summary = TelemetrySummary;

const runsOf = (total: number): string => (total > 0 ? `of ${formatNumber(total)} runs` : "No runs in window");

function pctLine(p: Pct | undefined): string {
  if (!p || p.n === 0) return "No runs in window";
  return `p95 ${formatMs(p.p95)} · n ${formatNumber(p.n)}`;
}

/** Known code → its label; unknown code → the code itself (developer page, so codes are fine). */
function codeLabel(h: Humanized): string {
  return h.known ? h.label : h.code;
}

function prices(cost: Summary["cost"]): string {
  const p = cost.prices_per_mtok;
  return `Per 1M tokens: ${formatUsd(p.input)} input · ${formatUsd(p.output)} output · ${formatUsd(p.cache_write)} cache write · ${formatUsd(p.cache_read)} cache read`;
}

export function SummaryMetrics({ summary }: { summary: Summary }) {
  const total = summary.runs.total;
  const completed = summary.runs.by_status.completed ?? 0;
  const failed = sumValues(summary.runs.by_status, ["failed", "cancelled", "interrupted"]);
  const std = summary.latency_ms.total_by_mode.standard;
  const res = summary.latency_ms.total_by_mode.research;
  const { per_run_mean: tokMean } = summary.tokens;
  const mc = summary.model_calls;
  const cost = summary.cost;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
      <StatTile
        label="Runs"
        value={formatNumber(total)}
        context={`${formatNumber(summary.runs.by_mode.standard ?? 0)} standard · ${formatNumber(summary.runs.by_mode.research ?? 0)} research`}
      />
      <StatTile label="Completed" value={formatNumber(completed)} context={total ? `${formatPercent(completed / total)} of ${formatNumber(total)} runs` : "No runs in window"} />
      <StatTile label="Failed or cancelled" value={formatNumber(failed)} context={total ? `${ofTotal(failed, total)} runs` : "No runs in window"} />
      <StatTile label="Standard latency p50" value={formatMs(std?.p50)} context={pctLine(std)} />
      <StatTile label="Research latency p50" value={formatMs(res?.p50)} context={pctLine(res)} />
      <StatTile
        label="Mean tokens per run"
        value={tokMean.input == null ? "-" : `${formatNumber(Math.round(tokMean.input))} / ${formatNumber(Math.round(tokMean.output ?? 0))}`}
        context="input / output, synthesis + research"
      />
      <StatTile
        label="Model calls per run"
        value={formatNumber(mc.per_run_mean, 2)}
        context={`${formatNumber(mc.total)} total${mc.n_runs_missing ? ` · not recorded for ${formatNumber(mc.n_runs_missing)} runs` : ""}`}
      />
      <StatTile label="Tool calls per run" value={formatNumber(summary.tool_calls.per_run_mean, 2)} context={`${formatNumber(summary.tool_calls.total)} total`} />
      <StatTile
        label="Estimated cost (list prices)"
        value={formatUsd(cost.total_usd)}
        context={`${formatUsd(cost.per_run_usd)} per run · ${formatNumber(cost.n_runs_with_usage)} runs with usage`}
        footnote={<span title={prices(cost)}>Estimate, not billed cost</span>}
      />
      <StatTile label="Regeneration rate" value={formatPercent(summary.rates.regeneration)} context={runsOf(total)} />
      <StatTile
        label="Verification fallback rate"
        value={formatPercent(summary.rates.verification_fallback)}
        context={`Research planner fallback ${formatPercent(summary.rates.planner_fallback)}`}
      />
      <StatTile label="Degraded share" value={formatPercent(summary.rates.degraded)} context={runsOf(total)} />
    </div>
  );
}

export function CostNote({ cost }: { cost: Summary["cost"] }) {
  return (
    <p className="mt-2 text-xs text-muted">
      Estimated cost (list prices) is computed from persisted token usage. {prices(cost)}. It is not a billed amount.
    </p>
  );
}

/** Latency column headers; the abbreviation is explained on hover and in the metric glossary. */
const P50 = <span title={glossaryTitle("p50")}>p50</span>;
const P95 = <span title={glossaryTitle("p50")}>p95</span>;

interface StageRow {
  key: string;
  label: string;
  note: string;
  pct: Pct;
}

export function StageLatencyTable({ summary }: { summary: Summary }) {
  const rows: StageRow[] = STAGE_ROWS.map((s) => ({ ...s, pct: summary.latency_ms.stages[s.key] ?? { p50: null, p95: null, n: 0 } }));
  const columns: Column<StageRow>[] = [
    { key: "stage", header: "Stage", cell: (r) => <span className="font-medium">{r.label}</span> },
    { key: "p50", header: P50, align: "right", cell: (r) => formatMs(r.pct.p50) },
    { key: "p95", header: P95, align: "right", cell: (r) => formatMs(r.pct.p95) },
    { key: "n", header: "Runs", align: "right", cell: (r) => formatNumber(r.pct.n) },
    { key: "note", header: "Measures", cell: (r) => <span className="text-sm text-muted">{r.note}</span> },
  ];
  return <Table caption="Stage latency, p50 and p95" columns={columns} rows={rows} rowKey={(r) => r.key} density="compact" />;
}

type ToolRow = Summary["tool_calls"]["by_tool"][number];

const count = (n: number): ReactNode => (n === 0 ? <span className="text-muted">0</span> : formatNumber(n));

export function ToolTable({ summary }: { summary: Summary }) {
  const columns: Column<ToolRow>[] = [
    { key: "tool", header: "Tool", cell: (r) => <span className="font-mono text-sm">{r.tool}</span> },
    { key: "n", header: "Calls", align: "right", cell: (r) => formatNumber(r.n) },
    { key: "ok", header: "Succeeded", align: "right", cell: (r) => count(r.ok) },
    { key: "truncated", header: "Truncated", align: "right", cell: (r) => count(r.truncated) },
    { key: "error", header: "Error", align: "right", cell: (r) => count(r.error) },
    { key: "denied", header: "Denied", align: "right", cell: (r) => count(r.denied) },
    { key: "timeout", header: "Timed out", align: "right", cell: (r) => count(r.timeout) },
    { key: "p50", header: P50, align: "right", cell: (r) => formatMs(r.p50_ms) },
    { key: "p95", header: P95, align: "right", cell: (r) => formatMs(r.p95_ms) },
  ];
  return (
    <Table
      caption="Research tool calls by tool"
      columns={columns}
      rows={summary.tool_calls.by_tool}
      rowKey={(r) => r.tool}
      density="compact"
      empty="No tool calls in this window."
    />
  );
}

const RETRIEVAL_TIMINGS: { key: keyof Summary["retrieval"]["timings"]; label: string }[] = [
  { key: "embed_ms", label: "Query embedding" },
  { key: "lexical_prep_ms", label: "Lexical query prep" },
  { key: "lexical_ms", label: "Lexical search" },
  { key: "dense_ms", label: "Dense search" },
  { key: "fusion_ms", label: "Fusion (reciprocal-rank)" },
  { key: "total_ms", label: "Total" },
];

const LANES: { key: keyof Summary["retrieval"]["candidates"]; label: string }[] = [
  { key: "lexical", label: "Lexical" },
  { key: "dense", label: "Dense" },
  { key: "fused", label: "Fused" },
  { key: "final", label: "Final" },
];

type TimingRow = (typeof RETRIEVAL_TIMINGS)[number];

const TIMING_COLUMNS = (r: Summary["retrieval"]): Column<TimingRow>[] => {
  const strong = (t: TimingRow, text: string) => (t.key === "total_ms" ? <span className="font-medium">{text}</span> : text);
  return [
    { key: "stage", header: "Stage", cell: (t) => strong(t, t.label) },
    { key: "p50", header: P50, align: "right", cell: (t) => strong(t, formatMs(r.timings[t.key]?.p50)) },
    { key: "p95", header: P95, align: "right", cell: (t) => strong(t, formatMs(r.timings[t.key]?.p95)) },
  ];
};

export function RetrievalSummary({ summary }: { summary: Summary }) {
  const r = summary.retrieval;
  if (r.n === 0) {
    return <NotRecorded>No retrieval traces in this window. Traces are written for standard searches only.</NotRecorded>;
  }
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Panel title="Candidates per lane" meta={`p50 across ${formatNumber(r.n)} traces`}>
        <dl className="grid grid-cols-4 gap-3">
          {LANES.map((l) => (
            <div key={l.key}>
              <dt className="text-sm text-muted">{l.label}</dt>
              <dd className="mt-0.5 text-lg font-semibold tabular-nums text-primary">{formatNumber(r.candidates[l.key].p50)}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 border-t border-border pt-2 text-sm text-secondary">
          Embedding cache hit rate:{" "}
          <span className="font-medium tabular-nums text-primary">{r.embedding_cache_hit_rate == null ? "Not recorded" : formatPercent(r.embedding_cache_hit_rate)}</span>
        </p>
      </Panel>
      <Table
        caption={`Sub-stage timings across ${formatNumber(r.n)} traces`}
        showCaption
        columns={TIMING_COLUMNS(r)}
        rows={RETRIEVAL_TIMINGS}
        rowKey={(t) => t.key}
        density="compact"
      />
    </div>
  );
}

function bars(items: { label: string; n: number }[], denom: number): BarItem[] {
  return items.map((i) => ({ label: i.label, value: i.n, display: denom > 0 ? `${formatNumber(i.n)} · ${formatPercent(i.n / denom)}` : formatNumber(i.n) }));
}

function BarPanel({ title, meta, items, empty }: { title: string; meta: string; items: BarItem[]; empty: string }) {
  return (
    <Panel title={title} meta={meta}>
      {items.length === 0 ? <NotRecorded>{empty}</NotRecorded> : <BarList layout="stacked" ariaLabel={title} items={items} />}
    </Panel>
  );
}

export function Auditability({ summary }: { summary: Summary }) {
  const total = summary.runs.total;
  const cov = summary.coverage;
  const verifyRuns = cov.runs_with_verification;
  const toolTotal = sumValues(summary.governance.tool_status);
  const route = summary.route_reasons.map((r) => ({ label: codeLabel(routeReason(r.reason)), n: r.n }));
  const dispositions = summary.verification.dispositions.map((d) => ({
    label: `#${d.attempt} ${codeLabel(verificationDisposition(d.disposition))}`,
    n: d.n,
  }));
  const failures = summary.verification.failure_categories.map((f) => ({ label: codeLabel(verificationFailure(f.category)), n: f.n }));
  const flags = summary.flags.map((f) => ({ label: codeLabel(degradationFlag(f.code)), n: f.n }));
  const status = Object.entries(summary.governance.tool_status).map(([s, n]) => ({ label: toolStatusLabel(s), n }));
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <BarPanel title="Route decision reasons" meta={`${formatNumber(cov.runs_with_route)} runs with a route record`} items={bars(route, cov.runs_with_route)} empty="No route decisions recorded in this window." />
      <BarPanel title="Verification dispositions" meta={`By attempt (#1, #2) · ${formatNumber(verifyRuns)} verified runs`} items={bars(dispositions, verifyRuns)} empty="No verification attempts recorded in this window." />
      <BarPanel title="Verification failure categories" meta="Count of attempts, per category" items={bars(failures, 0)} empty="No failed checks in this window." />
      <BarPanel title="Degradation flags" meta={`Share of ${formatNumber(total)} runs`} items={bars(flags, total)} empty="No degraded runs in this window." />
      <Panel className="lg:col-span-2" title="Governance" meta={`${formatNumber(toolTotal)} audited tool calls`}>
        <div className="grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          {toolTotal === 0 ? (
            <NotRecorded>No tool calls in this window.</NotRecorded>
          ) : (
            <BarList layout="stacked" ariaLabel="Tool call outcomes" items={bars(status, toolTotal)} />
          )}
          <dl className="grid content-start gap-3 text-sm md:border-l md:border-border md:pl-4">
            <div>
              <dt className="text-muted">Redacted tool arguments</dt>
              <dd className="font-medium tabular-nums text-primary">{formatNumber(summary.governance.redacted_tool_args)}</dd>
            </div>
            <div>
              <dt className="text-muted">Redacted messages</dt>
              <dd className="font-medium tabular-nums text-primary">{formatNumber(summary.governance.redacted_messages)}</dd>
            </div>
          </dl>
        </div>
      </Panel>
    </div>
  );
}

/** Explains which runs predate route, research and verification logging. */
export function CoverageNote({ summary }: { summary: Summary }) {
  const total = summary.runs.total;
  const research = summary.runs.by_mode.research ?? 0;
  const { runs_with_route: route, runs_with_agent: agent, runs_with_verification: verify } = summary.coverage;
  if (total === 0 || (route >= total && verify >= total && agent >= research)) return null;
  return (
    <Callout tone="neutral" title="Some runs predate detailed logging">
      Route decisions are recorded for {ofTotal(route, total)} runs, research-step records for {ofTotal(agent, research)} research runs and
      verification attempts for {ofTotal(verify, total)} runs. Runs logged before these records existed, and runs that stopped before
      synthesis, show &ldquo;Not recorded&rdquo; in those sections.
    </Callout>
  );
}

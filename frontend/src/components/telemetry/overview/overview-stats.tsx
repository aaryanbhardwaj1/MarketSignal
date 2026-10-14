import type { TelemetrySeriesPoint, TelemetrySummaryWithOutcomes } from "@/lib/api/contracts";
import { Sparkline } from "@/components/charts";
import { Stat } from "@/components/ui/stat";
import { formatMs, formatNumber, formatPercent, formatUsd } from "@/lib/format";
import { binRate, binSeries, formatCompact, mean, median } from "@/lib/telemetry-view";

/** Sparkline plus a sentence describing it (charts never speak by shape alone). */
function Trend({ values, what, format }: { values: number[]; what: string; format: (v: number) => string }) {
  if (values.length < 3) return null;
  const label = `${what}, in ${values.length} equal groups of runs in the order recorded: first group ${format(values[0])}, last group ${format(values[values.length - 1])}.`;
  return <Sparkline values={values} ariaLabel={label} width={72} height={22} />;
}

const tokensOf = (p: TelemetrySeriesPoint): number | null =>
  p.tokens_in == null && p.tokens_out == null ? null : (p.tokens_in ?? 0) + (p.tokens_out ?? 0);

/** The six headline figures. Sparklines appear only once the per-run series has loaded. */
export function OverviewStats({ summary, points }: { summary: TelemetrySummaryWithOutcomes; points: readonly TelemetrySeriesPoint[] | null }) {
  const total = summary.runs.total;
  const completed = summary.runs.by_status.completed ?? 0;
  const success = summary.rates.success ?? (total ? completed / total : null);
  const std = summary.latency_ms.total_by_mode.standard;
  const res = summary.latency_ms.total_by_mode.research;
  const tokens = summary.tokens;
  const tokenTotal = tokens.input + tokens.output;
  const tokenMean = tokens.per_run_mean.input == null ? null : (tokens.per_run_mean.input ?? 0) + (tokens.per_run_mean.output ?? 0);
  const cost = summary.cost;
  const pts = points ?? [];
  const stdPts = pts.filter((p) => p.mode === "standard");
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-6 md:grid-cols-3 xl:grid-cols-6 [&>*]:border-l [&>*]:border-border [&>*]:pl-4">
      <Stat
        label="Total runs"
        value={<span className="whitespace-nowrap">{formatNumber(total)}</span>}
        sub={`${formatNumber(summary.runs.by_mode.standard ?? 0)} Standard · ${formatNumber(summary.runs.by_mode.research ?? 0)} Research`}
      />
      <Stat
        label="Success rate"
        value={<span className="whitespace-nowrap">{formatPercent(success)}</span>}
        sub={`${formatNumber(completed)} of ${formatNumber(total)} completed`}
        trend={<Trend values={binRate(pts, (p) => p.status === "completed")} what="Share of runs completed" format={(v) => formatPercent(v)} />}
      />
      <Stat
        label="Standard p50 latency"
        value={<span className="whitespace-nowrap">{formatMs(std?.p50)}</span>}
        sub={`p95 ${formatMs(std?.p95)} · Research p50 ${formatMs(res?.p50)}`}
        trend={<Trend values={binSeries(stdPts.map((p) => p.total_ms), median)} what="Median Standard run latency" format={formatMs} />}
      />
      <Stat
        label="Total tokens"
        value={<span className="whitespace-nowrap">{formatCompact(tokenTotal)}</span>}
        sub={tokenMean == null ? "No token usage recorded" : `${formatNumber(Math.round(tokenMean))} per run (mean)`}
        trend={<Trend values={binSeries(pts.map(tokensOf), mean)} what="Mean tokens per run" format={(v) => formatNumber(Math.round(v))} />}
      />
      <Stat
        label="Estimated cost"
        value={<span className="whitespace-nowrap">{formatUsd(cost.total_usd)}</span>}
        sub={`${formatUsd(cost.per_run_usd)} per run · estimate`}
        trend={<Trend values={binSeries(pts.map((p) => p.est_cost_usd), mean)} what="Mean estimated cost per run" format={(v) => formatUsd(v)} />}
      />
      <Stat
        label="Verification fallback"
        value={<span className="whitespace-nowrap">{formatPercent(summary.rates.verification_fallback)}</span>}
        sub={`Regeneration ${formatPercent(summary.rates.regeneration)}`}
        trend={<Trend values={binRate(pts, (p) => p.disposition === "fallback")} what="Share of runs with a fallback answer" format={(v) => formatPercent(v)} />}
      />
    </div>
  );
}

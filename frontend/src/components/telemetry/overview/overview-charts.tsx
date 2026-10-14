"use client";

import type { ReactNode } from "react";
import type { TelemetrySeriesPoint, TelemetrySummary } from "@/lib/api/contracts";
import { ChartEmpty, GroupedBarChart, HBarChart, StackedBar } from "@/components/charts";
import { SectionHeader } from "@/components/ui/section-header";
import { formatMs, formatNumber } from "@/lib/format";
import { countByValue, latencyDots, modeStageMedians, outcomeBuckets, toolProblems } from "@/lib/telemetry-view";
import { LatencyScatter, type ModeReference } from "./latency-scatter";

/** One chart answering one question: a small heading, the chart, and its caption. */
function ChartBlock({ title, description, children, className }: { title: string; description: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={className}>
      <SectionHeader as="h3" title={title} description={description} />
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function LatencyChart({ summary, points, span }: { summary: TelemetrySummary; points: readonly TelemetrySeriesPoint[]; span: string | null }) {
  const refs: ModeReference[] = (["standard", "research"] as const).flatMap((mode) => {
    const p = summary.latency_ms.total_by_mode[mode];
    return p && p.n > 0 ? [{ mode, p50: p.p50, p95: p.p95 }] : [];
  });
  return (
    <ChartBlock
      title="How long does a run take?"
      description={`Runs in the window, in the order recorded${span ? ` (${span})` : ""}. Reference lines are each mode's p50 and p95 for the whole window.`}
    >
      <LatencyScatter
        dots={latencyDots(points)}
        references={refs}
        total={points.length}
        caption="The x-axis is run order, not elapsed time: runs recorded close together are spread evenly."
      />
    </ChartBlock>
  );
}

export function StageChart({ points }: { points: readonly TelemetrySeriesPoint[] }) {
  const std = modeStageMedians(points, "standard");
  const res = modeStageMedians(points, "research");
  const labels = Array.from(new Set([...res, ...std].map((s) => s.label)));
  const order = ["Research steps", "Retrieval", "Evidence pack", "Generation", "Verification"];
  const categories = order.filter((l) => labels.includes(l));
  const valueOf = (stages: typeof std, label: string) => stages.find((s) => s.label === label)?.ms ?? Number.NaN;
  const series = [
    ...(std.length ? [{ name: "Standard", values: categories.map((c) => valueOf(std, c)) }] : []),
    ...(res.length ? [{ name: "Research", values: categories.map((c) => valueOf(res, c)) }] : []),
  ];
  return (
    <ChartBlock title="Where does the time go?" description="Median time per stage, Standard vs Research. Only runs that performed a stage count towards it.">
      {series.length === 0 ? (
        <ChartEmpty message="No stage timings were recorded in this window." />
      ) : (
        <GroupedBarChart
          categories={categories}
          series={series}
          ariaLabel="Median stage latency by mode"
          format={formatMs}
          caption="Medians are not additive, so the stages need not sum to the median run time. Time to first token is listed under More metrics."
        />
      )}
    </ChartBlock>
  );
}

export function OutcomeChart({ points }: { points: readonly TelemetrySeriesPoint[] }) {
  const { present, absent, fallbackElsewhere } = outcomeBuckets(points);
  const notes = [
    absent.length ? `None in this window: ${absent.join(", ")}.` : null,
    fallbackElsewhere ? `${formatNumber(fallbackElsewhere)} fallback answers are counted under the outcome the run ended with.` : null,
  ].filter(Boolean);
  return (
    <ChartBlock title="How did runs end?" description="One outcome per run: run status first, then how it ended, then whether the answer fell back after failing citation checks.">
      {present.length === 0 ? (
        <ChartEmpty message="No runs in this window." />
      ) : (
        <StackedBar
          segments={present.map((b) => ({ label: b.label, value: b.n, color: b.color }))}
          ariaLabel="Run outcomes"
          format={(v) => formatNumber(v)}
          caption={notes.length ? notes.join(" ") : undefined}
        />
      )}
    </ChartBlock>
  );
}

export function ToolChart({ summary }: { summary: TelemetrySummary }) {
  const tools = summary.tool_calls.by_tool;
  const problems = tools.flatMap((t) => {
    const p = toolProblems(t);
    return p ? [`${t.tool}: ${p}`] : [];
  });
  return (
    <ChartBlock title="Which research tools run?" description={`Audited tool calls by tool; ${formatNumber(summary.tool_calls.total)} in total. Tools with any non-successful call are highlighted.`}>
      {tools.length === 0 ? (
        <ChartEmpty message="No research tool calls in this window." />
      ) : (
        <HBarChart
          data={tools.map((t) => ({ label: t.tool, value: t.n, emphasis: toolProblems(t) != null }))}
          ariaLabel="Tool calls by tool"
          valueLabel="Calls"
          format={(v) => formatNumber(v)}
          labelWidth="11rem"
          caption={problems.length ? `Not successful: ${problems.join("; ")}.` : "Every audited call succeeded."}
        />
      )}
    </ChartBlock>
  );
}

export function ModelCallChart({ points }: { points: readonly TelemetrySeriesPoint[] }) {
  const counts = countByValue(points.map((p) => p.model_calls));
  const missing = points.filter((p) => p.model_calls == null).length;
  return (
    <ChartBlock title="How many model calls per run?" description="Runs by the number of model calls each one recorded.">
      {counts.length === 0 ? (
        <ChartEmpty message="No run in this window recorded its model calls." />
      ) : (
        <HBarChart
          data={counts.map((c) => ({ label: `${c.value} call${c.value === 1 ? "" : "s"}`, value: c.n }))}
          ariaLabel="Runs by number of model calls"
          valueLabel="Runs"
          format={(v) => formatNumber(v)}
          labelWidth="5rem"
          caption={missing ? `Not recorded for ${formatNumber(missing)} runs.` : undefined}
        />
      )}
    </ChartBlock>
  );
}

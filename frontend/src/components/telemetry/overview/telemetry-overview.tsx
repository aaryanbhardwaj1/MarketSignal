import type { TelemetrySeries, TelemetrySummaryWithOutcomes } from "@/lib/api/contracts";
import { Disclosure } from "@/components/ui/disclosure";
import { SectionHeader } from "@/components/ui/section-header";
import { ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import { formatNumber } from "@/lib/format";
import { seriesSpan } from "@/lib/telemetry-view";
import { Auditability, CostNote, CoverageNote, RetrievalSummary, StageLatencyTable, ToolTable } from "../summary-panels";
import { LatencyChart, ModelCallChart, OutcomeChart, StageChart, ToolChart } from "./overview-charts";
import { OverviewStats } from "./overview-stats";
import { SecondaryMetrics, TelemetryGlossary } from "./secondary-metrics";

export interface SeriesState {
  data: TelemetrySeries | undefined;
  pending: boolean;
  error: unknown;
  retry: () => void;
}

function SeriesCharts({ summary, series }: { summary: TelemetrySummaryWithOutcomes; series: TelemetrySeries }) {
  const points = series.points;
  return (
    <div className="flex flex-col gap-10">
      {series.truncated && (
        <p className="text-xs text-muted">
          Charts show the {formatNumber(series.n)} most recent runs in the window; the figures above cover all {formatNumber(summary.runs.total)}.
        </p>
      )}
      <LatencyChart summary={summary} points={points} span={seriesSpan(points)} />
      <div className="grid gap-10 lg:grid-cols-2">
        <StageChart points={points} />
        <OutcomeChart points={points} />
      </div>
      <div className="grid gap-10 lg:grid-cols-2">
        <ToolChart summary={summary} />
        <ModelCallChart points={points} />
      </div>
    </div>
  );
}

/**
 * Overview tab: six headline figures, four charts that each answer one question, then secondary
 * figures and the detailed tables behind a disclosure. Everything is persisted telemetry.
 */
export function TelemetryOverview({ summary, series }: { summary: TelemetrySummaryWithOutcomes; series: SeriesState }) {
  return (
    <div className="flex flex-col gap-12">
      <OverviewStats summary={summary} points={series.data?.points ?? null} />
      <section aria-labelledby="telemetry-charts">
        <SectionHeader id="telemetry-charts" title="Runs in the window" description="Latency, stage timings, outcomes and tool use, from each run's persisted record." />
        <div className="mt-6">
          {series.pending ? (
            <LoadingRegion label="Loading per-run telemetry">
              <Skeleton height="16rem" />
            </LoadingRegion>
          ) : series.error || !series.data ? (
            <ErrorState title="Per-run telemetry could not be loaded" description="The headline figures above are still current. Try again." error={series.error} retry={series.retry} />
          ) : (
            <SeriesCharts summary={summary} series={series.data} />
          )}
        </div>
      </section>
      <section aria-labelledby="telemetry-more">
        <SectionHeader id="telemetry-more" title="More metrics" description="Totals, distributions and rates behind the figures above." />
        <div className="mt-4 flex flex-col gap-4">
          <SecondaryMetrics summary={summary} />
          <CostNote cost={summary.cost} />
          <CoverageNote summary={summary} />
          <Disclosure summary="Detailed tables: stage latency, tools, retrieval, routing and verification">
            <div className="flex flex-col gap-8">
              <StageLatencyTable summary={summary} />
              <ToolTable summary={summary} />
              <RetrievalSummary summary={summary} />
              <Auditability summary={summary} />
            </div>
          </Disclosure>
          <TelemetryGlossary />
        </div>
      </section>
    </div>
  );
}

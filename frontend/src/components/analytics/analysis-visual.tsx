"use client";

import type { Analysis } from "@/lib/api/contracts";
import { GroupedBarChart, HBarChart, LineChart, Sparkline } from "../charts";
import {
  chooseChart,
  groupedSeries,
  lineSeries,
  listingBars,
  topBars,
  valueFormatter,
} from "@/lib/views/analytics";
import { analysisState, formatListingCell, unitLabel } from "./analysis-format";

const MINI_BARS = 4;

/** Honest note shown instead of numbers when an analysis could not be recomputed or no longer matches. */
export function WithheldNote({ analysis }: { analysis: Analysis }) {
  const state = analysisState(analysis);
  return (
    <p className="text-sm text-secondary">
      <span className="font-medium text-primary">{state.label}.</span> {state.message}
    </p>
  );
}

/** The trend in words for a time series: "Jan-Mar 2026 $886,762 to Apr-Jun 2026 $2,146,098". */
function trendWords(x: readonly string[], values: readonly number[], fmt: (v: number) => string): string {
  const last = values.length - 1;
  return `${x[0]} ${fmt(values[0])} to ${x[last]} ${fmt(values[last])}`;
}

/**
 * The one small visual on an analysis tile: top groups as bars, a single big figure, or a
 * sparkline for a time series. Numbers are withheld unless the analysis was recomputed.
 */
export function AnalysisMiniVisual({ analysis }: { analysis: Analysis }) {
  const kind = chooseChart(analysis);
  const fmt = valueFormatter(analysis);
  switch (kind) {
    case "withheld":
      return <WithheldNote analysis={analysis} />;
    case "empty":
      return <p className="text-sm text-muted">The analysis ran but matched no records.</p>;
    case "single":
      return <p className="text-display font-semibold tabular-nums text-primary">{analysis.display}</p>;
    case "line": {
      const line = lineSeries(analysis);
      if (!line || line.values.length < 2) return null;
      const last = line.values.length - 1;
      return (
        <div className="flex items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-muted">{line.x[last]}</p>
            <p className="text-xl font-semibold tabular-nums text-primary">{fmt(line.values[last])}</p>
            <p className="text-xs tabular-nums text-muted">{`from ${fmt(line.values[0])} in ${line.x[0]}`}</p>
          </div>
          <Sparkline values={line.values} width={140} height={40} emphasis ariaLabel={`${analysis.title}: ${trendWords(line.x, line.values, fmt)}`} />
        </div>
      );
    }
    case "grouped": {
      const grouped = groupedSeries(analysis);
      if (!grouped) return null;
      return (
        <GroupedBarChart
          categories={grouped.categories}
          series={grouped.series}
          ariaLabel={analysis.title}
          format={fmt}
          height={150}
        />
      );
    }
    case "table": {
      const { measure, bars } = listingBars(analysis, MINI_BARS);
      if (!measure || bars.length === 0) return null;
      return (
        <HBarChart
          data={bars}
          ariaLabel={`${analysis.title}: ${measure.label}`}
          caption={`${measure.label}, top ${bars.length}`}
          valueLabel={measure.label}
          format={(v) => formatListingCell(measure.column, String(v))}
          labelWidth="11rem"
        />
      );
    }
    default: {
      const bars = topBars(analysis, MINI_BARS);
      const more = analysis.rows.length - bars.length;
      return (
        <HBarChart
          data={bars}
          ariaLabel={analysis.title}
          caption={more > 0 ? `Top ${bars.length} of ${analysis.rows.length}` : undefined}
          valueLabel={unitLabel(analysis.unit)}
          format={fmt}
          labelWidth="11rem"
        />
      );
    }
  }
}

/** The full result chart on the detail page; listings return null (they are tables). */
export function AnalysisResultChart({ analysis }: { analysis: Analysis }) {
  const kind = chooseChart(analysis);
  const fmt = valueFormatter(analysis);
  if (kind === "hbar") {
    return (
      <HBarChart
        data={topBars(analysis, analysis.rows.length)}
        ariaLabel={analysis.title}
        valueLabel={unitLabel(analysis.unit)}
        format={fmt}
        labelWidth="12rem"
      />
    );
  }
  if (kind === "grouped") {
    const grouped = groupedSeries(analysis);
    return grouped ? <GroupedBarChart categories={grouped.categories} series={grouped.series} ariaLabel={analysis.title} format={fmt} /> : null;
  }
  if (kind === "line") {
    const line = lineSeries(analysis);
    return line ? (
      <LineChart
        x={line.x}
        series={[{ name: unitLabel(analysis.unit), values: line.values }]}
        ariaLabel={`${analysis.title}: ${trendWords(line.x, line.values, fmt)}`}
        format={fmt}
        includeZero
      />
    ) : null;
  }
  if (kind === "single") return <p className="text-display font-semibold tabular-nums text-primary">{analysis.display}</p>;
  return null;
}

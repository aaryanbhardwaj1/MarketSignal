"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import type { Analysis, AnalysisRow } from "@/lib/api/contracts";
import { formatDateTime, formatNumber, humanizeColumn, tableLabel } from "@/lib/format";
import { evidenceLibraryHref, insightsHref, opportunityHref } from "@/lib/routes";
import { chooseChart, filterChips, interpretationView, populationLine } from "@/lib/views/analytics";
import { Callout } from "../ui/callout";
import { ClaimTag } from "../ui/claim-tag";
import { DevDetails } from "../ui/disclosure";
import { KeyValueList } from "../ui/key-value";
import { SectionHeader } from "../ui/section-header";
import { Segmented } from "../ui/segmented";
import { Table, type Column } from "../ui/table";
import { analysisState, formatListingCell, isNumericColumn, rowBase, rowLabel, unitLabel } from "./analysis-format";
import { AnalysisResultChart } from "./analysis-visual";

interface IndexedRow {
  index: number;
  row: AnalysisRow;
}

/** Titles for linked insights and opportunities; unknown ids fall back to a neutral label. */
export interface RelatedTitles {
  signals: ReadonlyMap<string, string>;
  opportunities: ReadonlyMap<string, string>;
}

const NO_TITLES: RelatedTitles = { signals: new Map(), opportunities: new Map() };

function ValueTable({ analysis }: { analysis: Analysis }) {
  const rows: IndexedRow[] = analysis.rows.map((row, index) => ({ index, row }));
  if (analysis.op === "filter_rows" && analysis.columns && analysis.columns.length > 0) {
    const columns: Column<IndexedRow>[] = analysis.columns.map((col) => ({
      key: col,
      header: humanizeColumn(col),
      align: isNumericColumn(analysis.rows, col) ? "right" : "left",
      cell: ({ row }) => <span className="tabular-nums">{formatListingCell(col, row.group[col])}</span>,
    }));
    return <Table caption={analysis.title} columns={columns} rows={rows} rowKey={(r) => String(r.index)} />;
  }
  const groupKeys = analysis.group_by.length > 0 ? analysis.group_by : Object.keys(analysis.rows[0]?.group ?? {});
  const hasBase = analysis.rows.some((r) => rowBase(r, analysis) != null);
  const columns: Column<IndexedRow>[] = [
    ...groupKeys.map((key) => ({ key: `g-${key}`, header: humanizeColumn(key), cell: ({ row }: IndexedRow) => rowLabel(row, [key]) })),
    {
      key: "value",
      header: unitLabel(analysis.unit),
      align: "right" as const,
      cell: ({ row }: IndexedRow) => <span className="font-medium tabular-nums">{row.display ?? "-"}</span>,
    },
    ...(hasBase
      ? [{ key: "base", header: "Base", align: "right" as const, cell: ({ row }: IndexedRow) => <span className="tabular-nums text-secondary">{rowBase(row, analysis) ?? "-"}</span> }]
      : []),
  ];
  return <Table caption={analysis.title} columns={columns} rows={rows} rowKey={(r) => String(r.index)} />;
}

function Result({ analysis }: { analysis: Analysis }) {
  const kind = chooseChart(analysis);
  const [view, setView] = useState<"chart" | "table">("chart");
  if (kind === "withheld") {
    const state = analysisState(analysis);
    return (
      <Callout tone={state.kind === "mismatch" ? "warn" : "neutral"} title={state.kind === "mismatch" ? "Numbers withheld" : "Result unavailable"}>
        {state.message}
      </Callout>
    );
  }
  if (kind === "empty") return <p className="text-base text-secondary">The analysis ran but matched no records.</p>;
  if (kind === "table") return <ValueTable analysis={analysis} />;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Segmented
          label="Show result as"
          visibleLabel={null}
          value={view}
          onChange={setView}
          options={[
            { value: "chart", label: "Chart" },
            { value: "table", label: "Table" },
          ]}
        />
      </div>
      {view === "chart" ? <AnalysisResultChart analysis={analysis} /> : <ValueTable analysis={analysis} />}
    </div>
  );
}

function Block({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-t border-border pt-6">
      <SectionHeader title={title} action={action} />
      {children}
    </section>
  );
}

function Interpretation({ analysis }: { analysis: Analysis }) {
  const view = interpretationView(analysis);
  if (view.kind === "absent") return null;
  return (
    <Block title="Interpretation">
      {view.kind === "shown" ? (
        <p className="max-w-prose text-base text-secondary">
          {view.text} <ClaimTag type="inference" size="sm" explain className="ml-0.5" />
        </p>
      ) : (
        <p className="text-base text-muted">
          Interpretation withheld: it could not be checked against the current result.
        </p>
      )}
    </Block>
  );
}

function UsedBy({ ws, analysis, titles }: { ws: string; analysis: Analysis; titles: RelatedTitles }) {
  const { signals, opportunities } = analysis.used_by;
  if (signals.length === 0 && opportunities.length === 0) return null;
  const linkClass = "rounded-sm text-base text-accent-text hover:underline";
  return (
    <Block title="Used by">
      <div className="grid gap-6 sm:grid-cols-2">
        {signals.length > 0 && (
          <div>
            <h3 className="text-sm text-muted">Insights</h3>
            <ul className="mt-1.5 flex flex-col gap-1.5">
              {signals.map((id) => (
                <li key={id}>
                  <Link href={`${insightsHref(ws)}#${encodeURIComponent(id)}`} className={linkClass}>
                    {titles.signals.get(id) ?? "Related insight"}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
        {opportunities.length > 0 && (
          <div>
            <h3 className="text-sm text-muted">Growth opportunities</h3>
            <ul className="mt-1.5 flex flex-col gap-1.5">
              {opportunities.map((id) => (
                <li key={id}>
                  <Link href={opportunityHref(ws, id)} className={linkClass}>
                    {titles.opportunities.get(id) ?? "Related opportunity"}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Block>
  );
}

/** The base a reader should hold the figures against, in plain words. */
function baseText(analysis: Analysis): string {
  if (analysis.denominator) return `${formatNumber(analysis.denominator.value)} ${analysis.denominator.label}`;
  if (analysis.op === "filter_rows") {
    const matched = analysis.provenance.rows_matched;
    return matched != null ? `${formatNumber(matched)} matching records; ${formatNumber(analysis.rows.length)} shown` : "Matching records, one per row";
  }
  return "Shown per row: each group has its own base";
}

/**
 * One analysis: what was measured, the result (chart or table), its interpretation (labelled
 * inference), what uses it, provenance, caveats and technical details. Presentational.
 */
export function AnalysisDetailView({ ws, analysis, titles = NO_TITLES }: { ws: string; analysis: Analysis; titles?: RelatedTitles }) {
  const prov = analysis.provenance;
  const listing = analysis.op === "filter_rows";
  const chips = filterChips(analysis);
  const population = populationLine(analysis);
  const base = baseText(analysis);
  const computed = analysis.status === "computed";

  const measured = [
    // When every figure is out of the whole population, say so once rather than twice.
    ...(population === base
      ? [{ label: "Population and base", value: base }]
      : [...(population ? [{ label: "Population", value: population }] : []), { label: "Base", value: base }]),
    {
      label: "Groups",
      value: analysis.group_by.length > 0 ? analysis.group_by.map((k) => humanizeColumn(k)).join(" and ") : listing ? "One row per record" : "Not grouped",
    },
    { label: "Unit", value: listing ? "As labelled in each column" : unitLabel(analysis.unit) },
  ];

  return (
    <div className="flex flex-col gap-8">
      <Block title="What was measured">
        <p className="max-w-prose text-md text-primary">{analysis.question}</p>
        <div className="flex flex-wrap items-center gap-2" aria-label="Filters">
          {chips.length > 0 ? (
            chips.map((c) => (
              <span key={c} className="inline-flex h-6 items-center rounded-md border border-border bg-sunken px-2 text-sm text-secondary">
                {c}
              </span>
            ))
          ) : (
            <span className="text-sm text-muted">No filters: all records in the dataset</span>
          )}
        </div>
        <KeyValueList items={measured} columns={2} />
      </Block>

      <Block
        title="Result"
        action={computed ? <span className="inline-flex items-center gap-2 text-sm text-muted"><ClaimTag type="derived" size="sm" /> Recomputed from the dataset</span> : undefined}
      >
        <Result analysis={analysis} />
      </Block>

      <Interpretation analysis={analysis} />

      <UsedBy ws={ws} analysis={analysis} titles={titles} />

      <Block
        title="Provenance"
        action={
          <Link
            href={evidenceLibraryHref(ws, { q: prov.source_title })}
            className="inline-flex items-center gap-1 rounded-sm text-sm font-medium text-accent-text hover:underline"
          >
            View source in Evidence library <ArrowRight aria-hidden className="size-3.5" />
          </Link>
        }
      >
        <KeyValueList
          columns={2}
          items={[
            { label: "Dataset", value: prov.source_title },
            { label: "Version", value: `Version ${prov.version}` },
            { label: "Table", value: tableLabel(prov.table) },
            { label: "Rows matched", value: prov.rows_matched != null ? formatNumber(prov.rows_matched) : "-" },
            { label: "Recomputed at", value: formatDateTime(prov.computed_at) },
          ]}
        />
      </Block>

      <Block title="Caveats">
        {analysis.caveats.length > 0 ? (
          <ul className="flex max-w-prose list-disc flex-col gap-1.5 pl-5 text-base text-secondary">
            {analysis.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        ) : (
          <p className="text-base text-muted">No caveats recorded for this analysis.</p>
        )}
      </Block>

      <DevDetails data={{ analysis_id: analysis.id, operation: analysis.op, dataset: prov.dataset, source_code: prov.source_code, spec: analysis.spec }} />
    </div>
  );
}

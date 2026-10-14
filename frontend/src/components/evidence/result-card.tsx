"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { ResultTableModel, TableRow } from "@/lib/analytics";
import { getResult } from "@/lib/api/endpoints";
import { useDatasets } from "@/lib/api/hooks/core";
import { queryKeys } from "@/lib/api/query-keys";
import type { AnalyticsResult } from "@/lib/api/types";
import { formatNumber, tableLabel } from "@/lib/format";
import { evidenceViewerHref } from "@/lib/handles";
import { HBarChart } from "../charts/hbar-chart";
import { ClaimTag } from "../ui/claim-tag";
import { DevDetails } from "../ui/disclosure";
import { KeyValueList } from "../ui/key-value";
import { ResultPanel } from "../ui/result-panel";
import { ErrorState, LoadingRegion } from "../ui/states";
import { Table, type Column } from "../ui/table";
import { useOptionalEvidenceDrawer } from "./drawer-context";
import { describeResult, plainMetrics, plainResultTable, resultBars } from "./result-display";

/** Every value below is rendered as a React text node: never as Markdown or HTML. */

type IndexedRow = TableRow & { index: number };

function RowLink({ ws, handle, text }: { ws: string; handle: string; text: string }) {
  const drawer = useOptionalEvidenceDrawer();
  return (
    <Link
      href={evidenceViewerHref(ws, handle)}
      onClick={(event) => {
        if (!drawer) return;
        event.preventDefault();
        drawer.openEvidence({ handle });
      }}
      className="text-accent-text hover:underline"
    >
      {text}
    </Link>
  );
}

function ResultTable({ ws, table }: { ws: string; table: ResultTableModel }) {
  const rows: IndexedRow[] = table.rows.map((row, index) => ({ ...row, index }));
  const columns: Column<IndexedRow>[] = table.headers.map((header, c) => ({
    key: `${c}`,
    header,
    align: c > 0 && rows.some((r) => r.cells[c]?.detail) ? "right" : "left",
    cell: (row) => {
      const cell = row.cells[c];
      if (!cell) return "-";
      const text = c === 0 && row.handle ? <RowLink ws={ws} handle={row.handle} text={cell.text} /> : cell.text;
      return (
        <span className={row.emphasis === "difference" ? "font-semibold" : undefined}>
          {text}
          {cell.detail && <span className="block text-xs font-normal text-muted">{cell.detail}</span>}
        </span>
      );
    },
  }));
  return <Table caption="Computed result table" columns={columns} rows={rows} rowKey={(r) => `${r.index}`} density="compact" />;
}

/**
 * Presentational view of a fetched analytics result, rendered through `ResultPanel`. Business
 * text only: dataset ids, source codes, the operation and the rounding policy are kept for
 * "Technical details". `sourceTitle` is the dataset title from the workspace dataset list.
 */
export function ResultCardView({ ws, result, sourceTitle }: { ws: string; result: AnalyticsResult; sourceTitle?: string | null }) {
  const view = describeResult(result);
  const table = plainResultTable(result);
  const title = sourceTitle ?? tableLabel(result.table);
  const details = [
    // A single figure already states its base; tables and listings state the match here.
    ...(view.value === undefined
      ? [{ label: "Records matched", value: `${formatNumber(result.rows_matched)} of ${formatNumber(result.rows_scanned)}` }]
      : []),
    ...(view.notes.length > 0 ? [{ label: "Calculation notes", value: view.notes.join("; ") }] : []),
  ];
  const computed = plainMetrics(result.spec);
  const bars = resultBars(result);
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <ClaimTag type="derived" size="sm" />
        Computed from a workspace dataset, not a quoted source.
      </p>
      <ResultPanel
        title={view.title}
        value={view.value}
        unit=""
        denominator={view.value !== undefined ? { label: "Base", value: view.base } : undefined}
        filters={view.filters.length > 0 ? view.filters : ["No filters"]}
        groupBy={view.groupBy}
        provenance={{ sourceTitle: title, sourceCode: result.source_code, version: result.source_version, table: result.table }}
      >
        {bars && (
          <HBarChart
            className="mb-3"
            ariaLabel={view.title}
            data={bars.map((b) => ({ label: b.label, value: b.value }))}
            format={(v) => bars.find((b) => b.value === v)?.display ?? formatNumber(v)}
          />
        )}
        {result.rows.length === 0 ? (
          <p className="text-secondary">No records matched, so nothing was computed.</p>
        ) : (
          table && <ResultTable ws={ws} table={table} />
        )}
        {(computed.length > 1 || details.length > 0) && (
          <div className={table || result.rows.length === 0 ? "mt-3" : undefined}>
            <KeyValueList items={[...(computed.length > 1 ? [{ label: "Computed", value: computed.join("; ") }] : []), ...details]} columns={2} />
          </div>
        )}
      </ResultPanel>
      <DevDetails
        data={{
          result_id: result.result_id,
          dataset: result.dataset,
          source_code: result.source_code,
          source_version: result.source_version,
          table: result.table,
          operation: result.operation,
          rounding: result.rounding,
          warnings: result.warnings,
          metrics: (result.rows[0]?.metrics ?? []).map((m) => m.key),
          spec: result.spec,
        }}
      />
    </div>
  );
}

/** Fetches `GET /results/{id}` (only mounted once the chip is opened) and renders the card. */
export function ResultCard({ ws, resultId }: { ws: string; resultId: string }) {
  const query = useQuery({
    queryKey: queryKeys.result(ws, resultId),
    queryFn: ({ signal }) => getResult(ws, resultId, signal),
    staleTime: Infinity, // a stored result is immutable
  });
  const datasets = useDatasets(ws);
  if (query.isPending) return <LoadingRegion label="Loading computed result" lines={5} />;
  if (query.isError) {
    return <ErrorState title="Could not load this computed result" error={query.error} retry={() => void query.refetch()} />;
  }
  const result = query.data.result;
  const sourceTitle = datasets.data?.datasets.find((d) => d.dataset === result.dataset)?.title ?? null;
  return <ResultCardView ws={ws} result={result} sourceTitle={sourceTitle} />;
}

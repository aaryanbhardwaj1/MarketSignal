"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  buildResultTable,
  denominatorText,
  describeFilters,
  describeGrouping,
  describeMetrics,
  formatMetricValue,
  type ResultTableModel,
} from "@/lib/analytics";
import { getResult } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { AnalyticsResult, MetricValue } from "@/lib/api/types";
import { describeError } from "@/lib/api/errors";
import { humanize } from "@/lib/format";
import { evidenceViewerHref } from "@/lib/handles";
import { errorMessage } from "@/lib/labels";
import { DevDetails } from "../ui/disclosure";
import { ErrorState, LoadingRegion } from "../ui/states";
import { useOptionalEvidenceDrawer } from "./drawer-context";

/** Every value below is rendered as a React text node: never as Markdown or HTML. */

function MetricList({ metrics }: { metrics: readonly MetricValue[] }) {
  return (
    <ul className="grid gap-2">
      {metrics.map((metric, i) => (
        <li key={`${metric.key}-${i}`} className="rounded-md border border-border bg-surface px-3 py-2">
          <p className="text-lg font-semibold tabular-nums text-primary">{formatMetricValue(metric)}</p>
          <p className="text-xs text-muted">{denominatorText(metric)}</p>
        </li>
      ))}
    </ul>
  );
}

function ResultTable({ ws, table }: { ws: string; table: ResultTableModel }) {
  const drawer = useOptionalEvidenceDrawer();
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-surface">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-surface-muted text-secondary">
          <tr>
            {table.headers.map((header, i) => (
              <th key={`${header}-${i}`} scope="col" className="px-2 py-1.5 font-semibold">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr
              key={r}
              className={`border-t border-border ${row.emphasis === "difference" ? "bg-surface-muted font-semibold" : ""}`}
            >
              {row.cells.map((cell, c) => (
                <td key={c} className="px-2 py-1.5 align-top text-primary">
                  {c === 0 && row.handle ? (
                    <Link
                      href={evidenceViewerHref(ws, row.handle)}
                      onClick={(event) => {
                        if (!drawer || !row.handle) return;
                        event.preventDefault();
                        drawer.openEvidence({ handle: row.handle });
                      }}
                      className="text-accent-text hover:underline"
                    >
                      {cell.text}
                    </Link>
                  ) : (
                    cell.text
                  )}
                  {cell.detail && <span className="ml-1 text-xs font-normal text-muted">({cell.detail})</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap gap-x-2">
      <dt className="font-medium text-muted">{label}</dt>
      <dd className="text-secondary">{children}</dd>
    </div>
  );
}

/** Presentational card for a fetched analytics result. */
export function ResultCardView({ ws, result }: { ws: string; result: AnalyticsResult }) {
  const filters = describeFilters(result.spec);
  const grouping = describeGrouping(result.spec);
  const requested = describeMetrics(result.spec);
  const table = buildResultTable(result);
  const metrics = result.rows[0]?.metrics ?? [];
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="text-xs font-medium text-cite-result">
        Computed result — deterministic calculation, not a quoted source
      </p>
      {result.rows.length === 0 ? (
        <p className="text-secondary">No rows matched, so nothing was computed.</p>
      ) : table ? (
        <ResultTable ws={ws} table={table} />
      ) : (
        <MetricList metrics={metrics} />
      )}
      <dl className="grid gap-1 text-xs">
        {requested.length > 0 && <Fact label="Computed">{requested.join("; ")}</Fact>}
        <Fact label="Filters">{filters.length > 0 ? filters.join("; ") : "No filters"}</Fact>
        {grouping.length > 0 && <Fact label="Grouped by">{grouping.join(", ")}</Fact>}
        <Fact label="Rows">
          {result.rows_matched.toLocaleString("en-US")} of {result.rows_scanned.toLocaleString("en-US")} matched
        </Fact>
        <Fact label="Dataset">
          {result.dataset} · source {result.source_code} v{result.source_version} · table {result.table}
        </Fact>
        <Fact label="Rounding">{result.rounding}</Fact>
        {result.warnings.length > 0 && (
          <Fact label="Notes">{result.warnings.map((w) => humanize(w)).join("; ")}</Fact>
        )}
      </dl>
      <DevDetails data={{ result_id: result.result_id, operation: result.operation, metrics: metrics.map((m) => m.key), spec: result.spec }} />
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
  if (query.isPending) return <LoadingRegion label="Loading computed result" lines={5} />;
  if (query.isError) {
    const { code } = describeError(query.error);
    return (
      <ErrorState
        title="Could not load this computed result"
        description={errorMessage(code).label}
        retry={() => void query.refetch()}
        devDetail={code}
      />
    );
  }
  return <ResultCardView ws={ws} result={query.data.result} />;
}

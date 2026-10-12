"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { AnalyticsResultSummary, DatasetInfo } from "@/lib/api/contracts";
import { useAnalyticsResults } from "@/lib/api/hooks/core";
import { useEvidenceDrawer } from "../evidence/drawer-context";
import { formatDate } from "@/lib/format";
import { EmptyState, ErrorState, LoadingRegion } from "../ui/states";
import { LoadMore } from "../ui/load-more";
import { Section } from "../ui/section";
import { Table, type Column } from "../ui/table";
import { tableLabel } from "./analysis-format";
import { describeResult } from "./result-summary";

const FIRST_ROWS = 10;
const MORE_ROWS = 20;

/** Table name only when it adds something beyond the dataset title. */
function tableNote(title: string, table: string): string | null {
  const plain = tableLabel(table);
  return plain.toLowerCase() === title.toLowerCase() ? null : `Table: ${plain}`;
}

/** Persisted computed results from research conversations; a row opens the result in the drawer. */
export function SavedResults({ ws, datasets }: { ws: string; datasets: readonly DatasetInfo[] }) {
  const query = useAnalyticsResults(ws, { includeTestRuns: false });
  const drawer = useEvidenceDrawer();
  const titles = useMemo(() => new Map(datasets.map((d) => [d.dataset, d])), [datasets]);
  const [visible, setVisible] = useState(FIRST_ROWS);
  const loaded = query.data?.pages.flatMap((p) => p.items) ?? [];
  const rows = loaded.slice(0, visible);
  const hasMore = loaded.length > visible || Boolean(query.hasNextPage);
  const showMore = () => {
    setVisible((v) => v + MORE_ROWS);
    if (loaded.length <= visible + MORE_ROWS && query.hasNextPage) void query.fetchNextPage();
  };

  const columns: Column<AnalyticsResultSummary>[] = [
    {
      key: "result",
      header: "Result",
      cell: (r) => {
        const d = describeResult(r);
        const info = titles.get(r.dataset);
        const title = r.tool === "filter_rows" && info && d.title === "Matching records" ? `${tableLabel(info.table)} records` : d.title;
        return (
          <div className="min-w-0">
            <p className="font-medium text-primary">{title}</p>
            {d.filters.length > 0 && <p className="mt-0.5 text-sm text-muted">{d.filters.join(" · ")}</p>}
          </div>
        );
      },
    },
    {
      key: "dataset",
      header: "Dataset",
      width: "17rem",
      cell: (r) => {
        const info = titles.get(r.dataset);
        return (
          <div>
            <p className="text-primary">{info?.title ?? "Dataset"}</p>
            <p className="text-sm text-muted">
              {[info ? tableNote(info.title, info.table) : null, `Version ${r.source_version}`].filter(Boolean).join(" · ")}
            </p>
          </div>
        );
      },
    },
    {
      key: "rows",
      header: "Rows matched",
      align: "right",
      width: "9rem",
      cell: (r) => <span className="whitespace-nowrap tabular-nums text-secondary">{describeResult(r).rowsMatched ?? "-"}</span>,
    },
    { key: "date", header: "Saved", width: "8rem", cell: (r) => <span className="whitespace-nowrap text-secondary">{formatDate(r.created_at)}</span> },
    {
      key: "conversation",
      header: "Conversation",
      width: "8rem",
      cell: (r) =>
        r.conversation_id ? (
          <Link
            href={`/w/${encodeURIComponent(ws)}/ask/${encodeURIComponent(r.conversation_id)}`}
            onClick={(e) => e.stopPropagation()}
            aria-label="Open the conversation this result came from"
            className="whitespace-nowrap rounded-sm text-sm font-medium text-accent-text hover:underline"
          >
            Open
          </Link>
        ) : (
          <span className="text-sm text-muted">-</span>
        ),
    },
  ];

  return (
    <Section
      title="From saved research"
      description="Figures computed while answering research questions, saved with the conversation they came from. Select a row to see the full result."
    >
      {query.isPending ? (
        <LoadingRegion label="Loading saved results" lines={4} />
      ) : query.isError ? (
        <ErrorState title="Saved results could not be loaded" description="Try again in a moment." retry={() => void query.refetch()} />
      ) : loaded.length === 0 ? (
        <EmptyState title="No saved results yet" description="Computed figures appear here once a research question has used a dataset." />
      ) : (
        <>
          <Table
            caption="Computed results saved from research conversations"
            columns={columns}
            rows={rows}
            rowKey={(r) => r.result_id}
            onRowClick={(r) => drawer.openResult(r.result_id)}
          />
          <LoadMore hasMore={hasMore} loading={query.isFetchingNextPage} onLoadMore={showMore} label="Show more results" />
        </>
      )}
    </Section>
  );
}

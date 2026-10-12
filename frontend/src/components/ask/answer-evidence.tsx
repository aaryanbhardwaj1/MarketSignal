"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import { ResultPanel } from "@/components/ui/result-panel";
import { Skeleton } from "@/components/ui/states";
import {
  buildResultTable,
  denominatorText,
  describeFilters,
  describeGrouping,
  describeMetrics,
  formatMetricValue,
} from "@/lib/analytics";
import { getResult } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { CitationCard, ResultCitationCard } from "@/lib/api/types";
import { evidenceViewerHref } from "@/lib/handles";
import { sourceClass, sourceType } from "@/lib/labels";

/** Consolidated evidence list; numbers match the inline citation chips. */
export function SupportingEvidenceList({ ws, cards }: { ws: string; cards: readonly CitationCard[] }) {
  const drawer = useOptionalEvidenceDrawer();
  return (
    <ol className="divide-y divide-border rounded-lg border border-border bg-surface">
      {cards.map((card, i) => {
        const meta = [sourceClass(card.source_class), sourceType(card.source_type)]
          .filter((l) => l.known)
          .map((l) => l.label);
        const label = `${card.source_title} · ${card.locator_label}`;
        return (
          <li key={card.handle} className="flex items-start gap-3 px-3 py-2.5">
            <span
              aria-hidden
              className="mt-0.5 inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-sm border border-cite-evidence/20 bg-cite-evidence-bg px-1 text-xs font-medium tabular-nums text-cite-evidence"
            >
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-medium text-primary">
                <span className="sr-only">Evidence {i + 1}: </span>
                {card.source_title}
              </p>
              <p className="text-sm text-muted">{[...meta, card.locator_label].join(" · ")}</p>
            </div>
            {drawer ? (
              <button
                type="button"
                aria-label={`Open passage: ${label}`}
                onClick={() =>
                  drawer.openEvidence({
                    handle: card.handle,
                    childId: card.anchor_child_id,
                    charStart: card.char_start ?? undefined,
                    charEnd: card.char_end ?? undefined,
                  })
                }
                className="shrink-0 rounded-sm text-sm font-medium text-accent-text hover:underline"
              >
                Open passage
              </button>
            ) : (
              <Link href={evidenceViewerHref(ws, card.handle, card.anchor_child_id)} className="shrink-0 text-sm font-medium text-accent-text hover:underline">
                Open passage
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** One computed result cited by the answer, as a ResultPanel (never shaped like evidence). */
function AnalyticsResultPanel({
  ws,
  card,
  number,
  sourceTitles,
}: {
  ws: string;
  card: ResultCitationCard;
  number: number;
  sourceTitles: Readonly<Record<string, string>>;
}) {
  const drawer = useOptionalEvidenceDrawer();
  const query = useQuery({
    queryKey: queryKeys.result(ws, card.result_id),
    queryFn: ({ signal }) => getResult(ws, card.result_id, signal),
    staleTime: Infinity,
  });
  if (query.isPending) return <Skeleton lines={3} />;
  const sourceTitle = sourceTitles[card.source_code] ?? "Workspace dataset";
  if (query.isError) {
    return (
      <ResultPanel
        title={`Computed result ${number}`}
        unit=""
        provenance={{ sourceTitle, sourceCode: card.source_code, version: card.source_version ?? "–", table: card.table ?? "–" }}
      >
        <p className="text-sm text-muted">The details of this computed result could not be loaded.</p>
      </ResultPanel>
    );
  }
  const result = query.data.result;
  const metrics = describeMetrics(result.spec);
  const table = buildResultTable(result);
  const single = !table && result.rows.length === 1 && result.rows[0].metrics.length === 1 ? result.rows[0].metrics[0] : null;
  const title = metrics.length > 0 ? metrics.join("; ") : "Computed figure";
  return (
    <ResultPanel
      title={`${number}. ${title.charAt(0).toUpperCase()}${title.slice(1)}`}
      value={single ? formatMetricValue(single) : undefined}
      unit=""
      denominator={single ? { label: "Base", value: denominatorText(single) } : undefined}
      filters={describeFilters(result.spec)}
      groupBy={describeGrouping(result.spec)}
      provenance={{ sourceTitle, sourceCode: result.source_code, version: result.source_version, table: result.table }}
    >
      {table && (
        <p className="text-sm text-secondary">
          {table.rows.length} {table.rows.length === 1 ? "row" : "rows"} computed; open the full result to see the table.
        </p>
      )}
      {drawer && (
        <button
          type="button"
          onClick={() => drawer.openResult(card.result_id)}
          className="mt-2 rounded-sm text-sm font-medium text-accent-text hover:underline"
        >
          Open full result
        </button>
      )}
    </ResultPanel>
  );
}

export function AnalyticsResults({
  ws,
  cards,
  sourceTitles,
}: {
  ws: string;
  cards: readonly ResultCitationCard[];
  sourceTitles: Readonly<Record<string, string>>;
}) {
  return (
    <div className="flex flex-col gap-3">
      {cards.map((card, i) => (
        <AnalyticsResultPanel key={card.result_id} ws={ws} card={card} number={i + 1} sourceTitles={sourceTitles} />
      ))}
    </div>
  );
}

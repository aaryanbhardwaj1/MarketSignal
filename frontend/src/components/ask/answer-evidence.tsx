"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import { ResultPanel } from "@/components/ui/result-panel";
import { Skeleton } from "@/components/ui/states";
import { describeResult } from "@/components/evidence/result-display";
import { DevDetails } from "@/components/ui/disclosure";
import { buildResultTable } from "@/lib/analytics";
import { getEvidence, getResult } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { CitationCard, Evidence, ResultCitationCard } from "@/lib/api/types";
import { businessLocator, parseRowPassage } from "@/lib/format";
import { evidenceViewerHref } from "@/lib/handles";
import { COMPUTED_FIGURE, sourceClass, sourceType } from "@/lib/labels";

const EXCERPT_FIELDS = 4;

/** One line of the cited passage: the highlighted quote, a few row fields, or the opening text. */
export function passageExcerpt(evidence: Evidence, card: Pick<CitationCard, "char_start" | "char_end">): string {
  if (evidence.highlight?.text) return evidence.highlight.text.trim();
  const { char_start: start, char_end: end } = card;
  const cited = typeof start === "number" && typeof end === "number" && end > start ? evidence.text.slice(start, end) : evidence.text;
  const fields = parseRowPassage(cited);
  if (fields) return fields.slice(0, EXCERPT_FIELDS).map((f) => `${f.label}: ${f.value}`).join(" · ");
  return cited.trim();
}

function Excerpt({ ws, card }: { ws: string; card: CitationCard }) {
  const query = useQuery({
    queryKey: queryKeys.evidence(ws, card.handle, card.anchor_child_id),
    queryFn: ({ signal }) => getEvidence(ws, card.handle, card.anchor_child_id, signal),
    staleTime: Infinity,
  });
  if (query.isPending) return <Skeleton lines={1} className="mt-1 max-w-sm" />;
  if (query.isError) return null;
  const text = passageExcerpt(query.data, card);
  if (!text) return null;
  return <p className="mt-0.5 line-clamp-2 text-sm text-secondary">“{text}”</p>;
}

function OpenPassage({ ws, card }: { ws: string; card: CitationCard }) {
  const drawer = useOptionalEvidenceDrawer();
  const label = `Open passage: ${card.source_title} · ${businessLocator(card.locator_label) || card.locator_label}`;
  const className = "shrink-0 rounded-sm text-sm font-medium text-accent-text hover:underline";
  if (!drawer) {
    return (
      <Link href={evidenceViewerHref(ws, card.handle, card.anchor_child_id)} aria-label={label} className={className}>
        Open passage
      </Link>
    );
  }
  return (
    <button
      type="button"
      aria-label={label}
      onClick={() =>
        drawer.openEvidence({
          handle: card.handle,
          childId: card.anchor_child_id,
          charStart: card.char_start ?? undefined,
          charEnd: card.char_end ?? undefined,
        })
      }
      className={className}
    >
      Open passage
    </button>
  );
}

interface SourceGroup {
  sourceCode: string;
  title: string;
  meta: string;
  items: { card: CitationCard; number: number }[];
}

/** Citations grouped by source in order of first citation; each keeps its answer-wide number. */
export function groupBySource(cards: readonly CitationCard[]): SourceGroup[] {
  const groups = new Map<string, SourceGroup>();
  cards.forEach((card, i) => {
    const key = card.source_code || card.source_title;
    let group = groups.get(key);
    if (!group) {
      const meta = [sourceClass(card.source_class), sourceType(card.source_type)].filter((l) => l.known).map((l) => l.label);
      group = { sourceCode: key, title: card.source_title, meta: meta.join(" · "), items: [] };
      groups.set(key, group);
    }
    group.items.push({ card, number: i + 1 });
  });
  return [...groups.values()];
}

/** Consolidated evidence list, grouped by source with a one-line excerpt per citation; numbers match the inline chips. */
export function SupportingEvidenceList({ ws, cards }: { ws: string; cards: readonly CitationCard[] }) {
  return (
    <div className="flex flex-col gap-3">
      {groupBySource(cards).map((group) => (
        <section key={group.sourceCode} aria-label={group.title} className="rounded-lg border border-border bg-surface">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 border-b border-border px-3 py-2">
            <p className="min-w-0 text-base font-medium text-primary">{group.title}</p>
            <p className="text-sm text-muted">
              {[group.meta, `${group.items.length} cited`].filter(Boolean).join(" · ")}
            </p>
          </div>
          <ol className="divide-y divide-border">
            {group.items.map(({ card, number }) => (
              <li key={card.handle} className="flex items-start gap-3 px-3 py-2.5">
                <span
                  aria-hidden
                  className="mt-0.5 inline-flex h-5 w-7 shrink-0 items-center justify-center rounded-sm border border-cite-evidence/20 bg-cite-evidence-bg text-xs font-medium tabular-nums text-cite-evidence"
                >
                  {number}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-primary">
                    <span className="sr-only">Evidence {number}: {group.title}, </span>
                    {businessLocator(card.locator_label) || card.locator_label}
                  </p>
                  <Excerpt ws={ws} card={card} />
                </div>
                <OpenPassage ws={ws} card={card} />
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

/** Name for one computed result, used by the inline chip, the panel and the drawer. */
export { COMPUTED_FIGURE } from "@/lib/labels";

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
        title={`${COMPUTED_FIGURE} ${number}`}
        unit=""
        provenance={{ sourceTitle, sourceCode: card.source_code, version: card.source_version ?? "–", table: card.table ?? "–" }}
      >
        <p className="text-sm text-muted">The details of this computed result could not be loaded.</p>
      </ResultPanel>
    );
  }
  const result = query.data.result;
  const view = describeResult(result);
  const table = buildResultTable(result);
  return (
    <ResultPanel
      title={`${number}. ${view.title}`}
      value={view.value}
      unit=""
      denominator={{ label: view.value !== undefined ? "Base" : "Records matched", value: view.base }}
      filters={view.filters}
      groupBy={view.groupBy}
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
      <div className="mt-2"><DevDetails data={{ result_id: result.result_id, operation: result.operation, source_code: result.source_code, table: result.table }} /></div>
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

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import { HBarChart } from "@/components/charts/hbar-chart";
import { Skeleton } from "@/components/ui/states";
import { datasetLine, describeResult, resultBars } from "@/components/evidence/result-display";
import { sourceKind } from "@/components/evidence/source-kind";
import { getEvidence, getResult } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { CitationCard, Evidence, ResultCitationCard } from "@/lib/api/types";
import { businessLocator, formatNumber, parseRowPassage } from "@/lib/format";
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
    <div className="flex flex-col gap-4">
      {groupBySource(cards).map((group) => (
        <section key={group.sourceCode} aria-label={group.title}>
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 border-b border-border pb-1.5">
            <p className="min-w-0 text-sm font-medium text-primary">{group.title}</p>
            <p className="text-sm text-muted">
              {[group.meta, `${group.items.length} cited`].filter(Boolean).join(" · ")}
            </p>
          </div>
          <ol className="divide-y divide-border">
            {group.items.map(({ card, number }) => (
              <li key={card.handle} className="flex items-start gap-3 py-2.5">
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

/** Opens a computed result in the drawer (falls back to nothing outside a workspace page). */
function OpenResult({ resultId, label }: { resultId: string; label: string }) {
  const drawer = useOptionalEvidenceDrawer();
  if (!drawer) return null;
  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => drawer.openResult(resultId)}
      className="shrink-0 rounded-sm text-sm font-medium text-accent-text hover:underline"
    >
      Open result
    </button>
  );
}

/** One computed result as a compact row: what was computed, the figure (or a mini chart), its base. */
function QuantitativeSignal({
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
  const query = useQuery({
    queryKey: queryKeys.result(ws, card.result_id),
    queryFn: ({ signal }) => getResult(ws, card.result_id, signal),
    staleTime: Infinity,
  });
  const sourceTitle = sourceTitles[card.source_code] ?? null;
  const marker = (
    <span
      aria-hidden
      className="mt-0.5 inline-flex h-5 min-w-7 shrink-0 items-center justify-center rounded-sm border border-cite-result/20 bg-cite-result-bg px-1 text-xs font-medium tabular-nums text-cite-result"
    >
      {number}
    </span>
  );
  if (query.isPending) {
    return (
      <li className="flex items-start gap-3 py-3">
        {marker}
        <Skeleton lines={2} className="flex-1" />
      </li>
    );
  }
  if (query.isError) {
    return (
      <li className="flex items-start gap-3 py-3">
        {marker}
        <p className="flex-1 text-sm text-muted">
          <span className="sr-only">{COMPUTED_FIGURE} {number}: </span>
          The details of this computed result could not be loaded.
        </p>
      </li>
    );
  }
  const result = query.data.result;
  const view = describeResult(result);
  const bars = resultBars(result);
  return (
    <li className="flex items-start gap-3 py-3">
      {marker}
      <div className="min-w-0 flex-1">
        <p className="text-sm text-primary">
          <span className="sr-only">{COMPUTED_FIGURE} {number}: </span>
          {view.title}
        </p>
        {view.value !== undefined && <p className="mt-1 text-xl font-semibold tabular-nums text-primary">{view.value}</p>}
        {bars && (
          <HBarChart
            className="mt-2"
            ariaLabel={view.title}
            data={bars.map((b) => ({ label: b.label, value: b.value }))}
            format={(v) => bars.find((b) => b.value === v)?.display ?? formatNumber(v)}
          />
        )}
        <p className="mt-1 text-xs text-muted">
          {[view.base, datasetLine(sourceTitle, result.source_version, result.table)].join(" · ")}
        </p>
      </div>
      <OpenResult resultId={card.result_id} label={`Open ${COMPUTED_FIGURE.toLowerCase()} ${number}: ${view.title}`} />
    </li>
  );
}

/** "Quantitative signals": every computed result the answer cites, numbered like its inline chip. */
export function QuantitativeSignals({
  ws,
  cards,
  sourceTitles,
}: {
  ws: string;
  cards: readonly ResultCitationCard[];
  sourceTitles: Readonly<Record<string, string>>;
}) {
  return (
    <ol className="divide-y divide-border border-y border-border">
      {cards.map((card, i) => (
        <QuantitativeSignal key={card.result_id} ws={ws} card={card} number={i + 1} sourceTitles={sourceTitles} />
      ))}
    </ol>
  );
}

/** Consolidated numbered source list at the end of an answer; each entry opens the evidence panel. */
export function SourcesList({ ws, cards }: { ws: string; cards: readonly CitationCard[] }) {
  const drawer = useOptionalEvidenceDrawer();
  return (
    <ol className="flex flex-col gap-1 text-sm">
      {cards.map((card, i) => {
        const locator = businessLocator(card.locator_label) || card.locator_label;
        const kind = sourceKind({ title: card.source_title, source_type: card.source_type, source_class: card.source_class });
        const content = (
          <>
            <span className="w-6 shrink-0 text-right tabular-nums text-muted">{i + 1}.</span>
            <span className="min-w-0">
              <span className="font-medium text-primary group-hover:text-accent-text">{card.source_title}</span>
              <span className="text-muted"> · {[kind, locator].filter(Boolean).join(" · ")}</span>
            </span>
          </>
        );
        const className = "group flex w-full gap-2 rounded-sm py-0.5 text-left";
        return (
          <li key={card.handle}>
            {drawer ? (
              <button
                type="button"
                className={className}
                onClick={() =>
                  drawer.openEvidence({
                    handle: card.handle,
                    childId: card.anchor_child_id,
                    charStart: card.char_start ?? undefined,
                    charEnd: card.char_end ?? undefined,
                  })
                }
              >
                {content}
              </button>
            ) : (
              <Link href={evidenceViewerHref(ws, card.handle, card.anchor_child_id)} className={className}>
                {content}
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}

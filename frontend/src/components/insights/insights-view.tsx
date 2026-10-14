"use client";

import { Presentation } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Callout } from "@/components/ui/callout";
import { LinkButton } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { SectionHeader } from "@/components/ui/section-header";
import type { EvidenceRef, InsightsBrief, Signal } from "@/lib/api/contracts";
import { formatCount, formatDateTime, formatRelativeDate } from "@/lib/format";
import type { AnalysisIndex } from "@/lib/insights-view";
import { insightsDeckHref, opportunitiesHref } from "@/lib/routes";
import {
  INSIGHT_CATEGORIES,
  categoryCounts,
  deckSelectionFor,
  groupSignals,
  opportunityKey,
  possessive,
  signalKey,
  type InsightCategory,
} from "@/lib/views/insights";
import { CategoryFilter, type CategoryFilterValue } from "./category-filter";
import { InsightCard } from "./insight-card";
import { InsightsSummary } from "./insights-summary";
import { OpportunitySummaries } from "./opportunity-summaries";
import { SelectionBar } from "./selection-bar";

export function insightsDescription(client: string | null | undefined): string {
  const who = client ? possessive(client) : "this client's";
  return `Evidence-backed patterns and what they mean for ${who} growth.`;
}

/** Curated-brief provenance, kept quiet: when it was last re-verified, and whether sources drifted. */
function Provenance({ brief, now }: { brief: InsightsBrief; now?: Date }) {
  return (
    <span>
      {brief.label} · re-verified against current evidence{" "}
      <time dateTime={brief.computed_at} title={formatDateTime(brief.computed_at)}>
        {formatRelativeDate(brief.computed_at, now)}
      </time>
    </span>
  );
}

function CategorySection({
  category,
  count,
  children,
}: {
  category: { id: string } & Pick<InsightCategory, "label" | "description">;
  count: number;
  children: ReactNode;
}) {
  const headingId = `insights-${category.id}`;
  return (
    <section aria-labelledby={headingId} className="scroll-mt-24">
      <SectionHeader
        id={headingId}
        title={
          <>
            {category.label} <span className="font-normal tabular-nums text-muted">{count}</span>
          </>
        }
        description={category.description}
      />
      <div className="mt-3">{children}</div>
    </section>
  );
}

function SignalList(props: {
  ws: string;
  signals: Signal[];
  brief: InsightsBrief;
  analyses: AnalysisIndex;
  isSelected: (key: string) => boolean;
  onToggle: (key: string) => void;
  onOpen?: (ref: EvidenceRef) => void;
}) {
  const { signals, isSelected, onToggle, ...rest } = props;
  return (
    <div className="divide-y divide-border rounded-lg border border-border bg-surface">
      {signals.map((s) => (
        <InsightCard
          key={s.id}
          signal={s}
          selected={isSelected(signalKey(s.id))}
          onToggle={(id) => onToggle(signalKey(id))}
          {...rest}
        />
      ))}
    </div>
  );
}

const toggled = (set: ReadonlySet<string>, key: string): Set<string> => {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
};

/**
 * The Insights page body for a loaded brief: header with the one primary action, a compact summary
 * band, category filter, the categories themselves and a sticky selection bar for the deck.
 */
export function InsightsView({
  ws,
  brief,
  analyses,
  client,
  onOpen,
  now,
}: {
  ws: string;
  brief: InsightsBrief;
  analyses: AnalysisIndex;
  client?: string | null;
  onOpen?: (ref: EvidenceRef) => void;
  /** Injectable clock for the relative "re-verified" time (tests). */
  now?: Date;
}) {
  const [filter, setFilter] = useState<CategoryFilterValue>("all");
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const { byKind, unclassified } = groupSignals(brief.signals);
  const counts = categoryCounts(brief);
  const deckHref = insightsDeckHref(ws, deckSelectionFor(brief, selected));
  const isSelected = (key: string) => selected.has(key);
  const onToggle = (key: string) => setSelected((prev) => toggled(prev, key));
  const visible = INSIGHT_CATEGORIES.filter((c) => (filter === "all" || filter === c.id) && counts[c.id] > 0);
  const listProps = { ws, brief, analyses, isSelected, onToggle, onOpen };

  return (
    <>
      <PageHeader
        title="Insights"
        description={insightsDescription(client)}
        meta={<Provenance brief={brief} now={now} />}
        divider={false}
        actions={
          <div className="flex flex-col items-end gap-1">
            <LinkButton href={deckHref} variant="primary" iconLeft={<Presentation aria-hidden size={16} />}>
              {selected.size > 0 ? `Create presentation (${selected.size})` : "Create presentation"}
            </LinkButton>
            <p className="max-w-64 text-right text-xs text-muted">
              {selected.size > 0
                ? `From ${formatCount(selected.size, "selected finding")}.`
                : `Starts from the ${formatCount(brief.opportunities.length, "strategic opportunity", "strategic opportunities")}. Select findings to choose your own.`}
            </p>
          </div>
        }
      />
      {brief.corpus_check.status === "drift" && (
        <div className="mb-2">
          <Callout tone="warn" title="Some findings could not be re-verified against current evidence">
            Sources have changed since this brief was prepared. Affected findings show without figures until an
            analyst reviews them.
          </Callout>
        </div>
      )}
      <InsightsSummary signals={brief.signals} opportunityCount={brief.opportunities.length} />

      <div className="sticky top-0 z-10 -mx-1 border-b border-border bg-canvas/95 py-2">
        <CategoryFilter value={filter} counts={counts} total={brief.signals.length + brief.opportunities.length} onChange={setFilter} />
      </div>

      <div className="mt-6 flex flex-col gap-10">
        {visible.map((c) => (
          <CategorySection key={c.id} category={c} count={counts[c.id]}>
            {c.id === "opportunities" ? (
              <>
                <OpportunitySummaries
                  ws={ws}
                  opportunities={brief.opportunities}
                  isSelected={(id) => isSelected(opportunityKey(id))}
                  onToggle={(id) => onToggle(opportunityKey(id))}
                />
                <p className="mt-2 text-sm">
                  <Link href={opportunitiesHref(ws)} className="text-accent-text hover:underline">
                    Weigh each opportunity in Growth Opportunities
                  </Link>
                </p>
              </>
            ) : (
              <SignalList signals={byKind[c.id]} {...listProps} />
            )}
          </CategorySection>
        ))}
        {filter === "all" && unclassified.length > 0 && (
          <CategorySection
            category={{ id: "other", label: "Other findings", description: "Findings without a category." }}
            count={unclassified.length}
          >
            <SignalList signals={unclassified} {...listProps} />
          </CategorySection>
        )}
      </div>

      <SelectionBar count={selected.size} href={deckHref} onClear={() => setSelected(new Set())} />
    </>
  );
}

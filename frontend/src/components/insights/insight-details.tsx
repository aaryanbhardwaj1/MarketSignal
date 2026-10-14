"use client";

import type { ReactNode } from "react";
import type { EvidenceRef, Signal } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { RowFields } from "@/components/ui/row-fields";
import { businessLocator, parseRowPassage } from "@/lib/format";
import { evidenceView } from "@/lib/insights-view";
import { isTabularSource } from "@/lib/labels";
import type { RelatedLink } from "@/lib/views/insights";
import { RelatedLinks } from "./insight-parts";

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="min-w-0">
      <h4 className="text-xs font-medium text-muted">{title}</h4>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

const ROLE_LABEL: Record<EvidenceRef["role"], string> = { support: "Supports", contradict: "Contradicts" };

function Passage({ evidence, onOpen }: { evidence: EvidenceRef; onOpen?: (ref: EvidenceRef) => void }) {
  const view = evidenceView(evidence);
  const where = [view.sourceTitle, businessLocator(view.locator)].filter(Boolean).join(" · ");
  // Spreadsheet and CSV rows read as labelled fields, as in the evidence drawer, not "column: value; ...".
  const fields = view.quote && isTabularSource(evidence.source.source_type) ? parseRowPassage(view.quote) : null;
  return (
    <li
      className={cx(
        "border-l-2 pl-3",
        evidence.role === "contradict" ? "border-l-contradicting" : "border-l-accent-muted",
      )}
    >
      <p className="text-xs text-muted">
        <span className={cx("font-medium", evidence.role === "contradict" ? "text-contradicting" : "text-secondary")}>
          {ROLE_LABEL[evidence.role]}
        </span>
        <span aria-hidden> · </span>
        {where}
        {evidence.states_projection && <span> · states a projection</span>}
      </p>
      {fields ? (
        <RowFields fields={fields} className="mt-1 text-sm!" />
      ) : view.quote ? (
        <blockquote className="mt-1 text-sm text-primary">&ldquo;{view.quote}&rdquo;</blockquote>
      ) : (
        <p className="mt-1 text-sm text-muted">
          {view.kind === "stale" ? "This passage changed since the brief was written." : "This source is no longer available."}
        </p>
      )}
      {evidence.note && <p className="mt-1 text-xs text-secondary">{evidence.note}</p>}
      {view.openable && onOpen && (
        <button type="button" onClick={() => onOpen(evidence)} className="mt-1 text-xs text-accent-text hover:underline">
          Open passage
        </button>
      )}
    </li>
  );
}

function TextList({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-0.5 pl-5 text-sm text-secondary">
      {items.map((t) => (
        <li key={t}>{t}</li>
      ))}
    </ul>
  );
}

/** Everything behind one insight: each cited passage, caveats, evidence gaps and related items. */
export function InsightDetails({
  signal,
  links,
  onOpen,
}: {
  signal: Signal;
  links: RelatedLink[];
  onOpen?: (ref: EvidenceRef) => void;
}) {
  const showGaps = signal.kind !== "future_outlook" && signal.gaps.length > 0;
  return (
    <div className="mt-4 grid gap-5 border-t border-border pt-4 xl:grid-cols-[minmax(0,1fr)_16rem]">
      <Block title={`Evidence (${signal.evidence.length})`}>
        {signal.evidence.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {signal.evidence.map((e, i) => (
              <Passage key={`${e.handle}-${i}`} evidence={e} onOpen={onOpen} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No cited passages.</p>
        )}
      </Block>
      <div className="flex flex-col gap-4">
        {showGaps && (
          <Block title="Evidence gaps">
            <TextList items={signal.gaps} />
          </Block>
        )}
        {signal.caveats.length > 0 && (
          <Block title="Caveats">
            <TextList items={signal.caveats} />
          </Block>
        )}
        {links.length > 0 && (
          <Block title="Related">
            <RelatedLinks links={links} />
          </Block>
        )}
      </div>
    </div>
  );
}

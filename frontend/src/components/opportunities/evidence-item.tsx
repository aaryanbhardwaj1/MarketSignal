"use client";

import { Badge } from "@/components/ui/badge";
import { EvidenceCard } from "@/components/ui/evidence-card";
import type { EvidenceRef } from "@/lib/api/contracts";
import { businessLocator } from "@/lib/format";
import { evidenceView } from "@/lib/insights-view";
import { sourceClass, sourceType } from "@/lib/labels";

function SourceLine({ evidence }: { evidence: EvidenceRef }) {
  return (
    <p className="mt-0.5 text-sm text-muted">
      {[sourceClass(evidence.source.source_class).label, sourceType(evidence.source.source_type).label, businessLocator(evidence.locator_label)]
        .filter(Boolean)
        .join(" · ")}
    </p>
  );
}

function AnalystNote({ note, inset = false }: { note: string | null; inset?: boolean }) {
  if (!note) return null;
  return (
    <p className={inset ? "mt-2 text-sm text-secondary" : "mt-1.5 px-4 text-sm text-secondary"}>
      <span className="font-medium text-primary">Analyst note: </span>
      {note}
    </p>
  );
}

/**
 * One cited passage on an opportunity. Verified passages show the quote and open the drawer at
 * the exact span; a passage changed since the brief opens without a quote; a withdrawn source is
 * replaced by a calm "no longer available" card.
 */
export function EvidenceItem({ evidence, onOpen }: { evidence: EvidenceRef; onOpen?: (ref: EvidenceRef) => void }) {
  const view = evidenceView(evidence);
  const open = onOpen && view.openable ? () => onOpen(evidence) : undefined;

  if (view.kind === "verified" && view.quote) {
    return (
      <li>
        <EvidenceCard
          source={{
            title: evidence.source.title,
            type: sourceType(evidence.source.source_type).label,
            classLabel: sourceClass(evidence.source.source_class).label,
            version: evidence.source.version,
          }}
          locator={evidence.locator_label}
          quote={view.quote}
          onOpen={open}
        />
        <AnalystNote note={evidence.note} />
      </li>
    );
  }

  const withdrawn = view.kind === "withdrawn";
  return (
    <li>
      <article className="rounded-lg border border-dashed border-border-strong bg-surface-muted p-4">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h4 className="truncate text-base font-medium text-primary">{evidence.source.title}</h4>
            <SourceLine evidence={evidence} />
          </div>
          <Badge tone={withdrawn ? "danger" : "warn"}>
            {withdrawn ? "Source no longer available" : "Source updated since"}
          </Badge>
        </header>
        <p className="mt-3 text-sm text-secondary">
          {withdrawn
            ? "This source was removed from the workspace, so the passage cannot be shown."
            : "The cited passage could not be found in the current version of this source. Review the source before relying on it."}
        </p>
        {open && (
          <button
            type="button"
            onClick={open}
            aria-label={`Open source passage: ${[evidence.source.title, businessLocator(evidence.locator_label)].filter(Boolean).join(", ")}`}
            className="mt-3 rounded-sm text-sm font-medium text-accent-text hover:underline"
          >
            Open source passage
          </button>
        )}
        <AnalystNote note={evidence.note} inset />
      </article>
    </li>
  );
}

"use client";

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import Link from "next/link";
import { getEvidence } from "@/lib/api/endpoints";
import { describeError, isApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/query-keys";
import type { Evidence, Tombstone } from "@/lib/api/types";
import { businessLocator, formatDate, parseRowPassage } from "@/lib/format";
import { isUuid } from "@/lib/handles";
import { resolveActiveSpan, segmentHighlight, type ActiveSpan } from "@/lib/highlight";
import { errorMessage, isTabularSource, sourceClass } from "@/lib/labels";
import { RowFields } from "../ui/row-fields";
import { Callout } from "../ui/callout";
import { DevDetails, Disclosure } from "../ui/disclosure";
import { ErrorState, LoadingRegion } from "../ui/states";
import { ChildSpanList } from "./child-span-list";
import { ContextExcerpts } from "./context-excerpts";
import { HighlightedText } from "./highlighted-text";
import { sourceKind } from "./source-kind";
import { VersionNotice } from "./version-notice";
import { sourceHref } from "@/lib/routes";

/** Optional span hint passed by the opener (a citation that knows offsets but no child id). */
export interface SpanHint {
  handle: string;
  childId: string | null;
  charStart?: number;
  charEnd?: number;
  quote?: string;
}

/** The API rejects non-UUID child ids with a 422; they are dropped client-side. */
const validChild = (childId: string | null): string | null => (childId && isUuid(childId) ? childId : null);

export function useEvidencePassage(ws: string, handle: string, childId: string | null): UseQueryResult<Evidence> {
  const child = validChild(childId);
  return useQuery({
    queryKey: queryKeys.evidence(ws, handle, child),
    queryFn: ({ signal }) => getEvidence(ws, handle, child, signal),
    enabled: Boolean(ws && handle),
    staleTime: Infinity, // a handle resolves to immutable text
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[3] === handle ? keepPreviousData(prev) : undefined),
  });
}

/** Span to mark: the requested child, else the opener's offsets, else the server highlight. */
export function pickSpan(evidence: Evidence, childId: string | null, hint: SpanHint | null): ActiveSpan | null {
  const child = validChild(childId);
  if (child) {
    const span = resolveActiveSpan(evidence, child);
    if (span) return span;
  }
  if (hint && typeof hint.charStart === "number" && typeof hint.charEnd === "number") {
    return { childId: "", charStart: hint.charStart, charEnd: hint.charEnd, expectedText: null };
  }
  return resolveActiveSpan(evidence, null);
}

function readTombstone(error: unknown): Tombstone | null {
  if (!isApiError(error)) return null;
  const t = error.details.tombstone;
  return t && typeof t === "object" ? (t as Tombstone) : null;
}

function PassageError({ error, handle, onRetry }: { error: unknown; handle: string; onRetry: () => void }) {
  const { code } = describeError(error);
  const status = isApiError(error) ? error.status : 0;
  if (code === "SOURCE_DELETED" || status === 410) {
    const t = readTombstone(error);
    return (
      <div className="flex flex-col gap-3">
        <Callout tone="neutral" title={t ? `This source was removed on ${formatDate(t.deleted_at)}` : "This source was removed"}>
          {t ? `"${t.title}" (version ${t.version}) is no longer available, so the passage text cannot be shown.` : "The passage text is no longer available."}
        </Callout>
        <DevDetails data={{ code, handle, tombstone: t }} />
      </div>
    );
  }
  if (code === "EVIDENCE_NOT_FOUND" || code === "MALFORMED_HANDLE" || status === 404 || status === 400) {
    return (
      <div className="flex flex-col gap-3">
        <Callout tone="neutral" title="Evidence not found">
          This passage could not be found in this workspace. The link may be incomplete or point to another workspace.
        </Callout>
        <DevDetails data={{ code, handle }} />
      </div>
    );
  }
  return (
    <ErrorState
      title="Could not load this passage"
      description={errorMessage(code).label}
      retry={onRetry}
      devDetail={`${code} · ${handle}`}
    />
  );
}

/** Source title, then its plain kind ("Survey", "Strategy memo"…) and class. */
function SourceSummary({ evidence }: { evidence: Evidence }) {
  const s = evidence.source;
  const cls = sourceClass(s.source_class);
  const kind = sourceKind({ title: s.title, source_type: s.source_type, source_class: s.source_class });
  return (
    <header className="flex flex-col gap-1">
      <h3 className="text-lg font-semibold leading-snug text-primary">{s.title}</h3>
      <p className="text-sm text-secondary">{[kind, cls.known ? cls.label : null].filter(Boolean).join(" · ")}</p>
    </header>
  );
}

/** Version, ingestion date and whether this is the current version; superseded passages get the notice. */
function Provenance({ ws, evidence }: { ws: string; evidence: Evidence }) {
  const s = evidence.source;
  const items = [
    { label: "Version", value: `Version ${s.version}` },
    ...(s.ingested_at ? [{ label: "Ingested", value: formatDate(s.ingested_at) }] : []),
    { label: "Status", value: s.is_latest ? "Current version" : "Earlier version of this source" },
  ];
  return (
    <section aria-label="Provenance" className="flex flex-col gap-3 border-t border-border pt-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">Provenance</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
        {items.map((item) => (
          <div key={item.label} className="contents">
            <dt className="text-muted">{item.label}</dt>
            <dd className="tabular-nums text-primary">{item.value}</dd>
          </div>
        ))}
      </dl>
      <VersionNotice ws={ws} handle={evidence.handle} source={s} />
      <p className="text-sm">
        <Link href={sourceHref(ws, s.source_id)} className="font-medium text-accent-text hover:underline">
          View source in Evidence Library
        </Link>
      </p>
    </section>
  );
}

/** Spreadsheet and CSV rows as labelled fields; other passages as text with the cited span marked. */
function PassageBody({ evidence, span }: { evidence: Evidence; span: ActiveSpan | null }) {
  const fields = isTabularSource(evidence.source.source_type) ? parseRowPassage(evidence.text) : null;
  if (!fields) return <HighlightedText text={evidence.text} span={span} />;
  const valid = span ? segmentHighlight(evidence.text, span.charStart, span.charEnd).valid : false;
  return (
    <div role="region" aria-label="Evidence passage" className="rounded-md border border-border bg-surface-muted px-4 py-3">
      <RowFields fields={fields} highlight={valid && span ? { start: span.charStart, end: span.charEnd } : null} />
    </div>
  );
}

/** Presentational passage view (no fetching), used by the drawer and its tests. */
export function EvidencePassageView({
  ws,
  evidence,
  span,
  onSelectChild,
}: {
  ws: string;
  evidence: Evidence;
  span: ActiveSpan | null;
  onSelectChild?: (childId: string | null) => void;
}) {
  const headings = evidence.heading_path.filter(Boolean);
  const hasContext = Boolean(evidence.context.previous_excerpt || evidence.context.next_excerpt);
  return (
    <div className="flex flex-col gap-5">
      <SourceSummary evidence={evidence} />

      <section aria-labelledby="evidence-passage-label" className="flex flex-col gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Cited passage</p>
          <h4 id="evidence-passage-label" className="mt-0.5 text-sm font-semibold text-primary">
            {businessLocator(evidence.locator_label) || "Passage"}
          </h4>
          {headings.length > 0 && <p className="text-sm text-muted">{headings.join(" / ")}</p>}
        </div>
        <PassageBody evidence={evidence} span={span} />
      </section>

      {hasContext && (
        <Disclosure variant="plain" summary="Show surrounding text">
          <div className="mt-2">
            <ContextExcerpts previous={evidence.context.previous_excerpt} next={evidence.context.next_excerpt} />
          </div>
        </Disclosure>
      )}

      {onSelectChild && evidence.children.length > 1 && (
        <Disclosure variant="plain" summary={`Parts of this passage (${evidence.children.length})`}>
          <ChildSpanList
            text={evidence.text}
            spans={evidence.children}
            activeId={span?.childId || null}
            onSelect={onSelectChild}
          />
        </Disclosure>
      )}

      <Provenance ws={ws} evidence={evidence} />

      <DevDetails
        data={{
          handle: evidence.handle,
          child_id: span?.childId || null,
          span: span ? [span.charStart, span.charEnd] : null,
          content_hash: evidence.content_hash,
          locator: evidence.locator,
          locator_label: evidence.locator_label,
          source_version: evidence.source.version,
          source_id: evidence.source.source_id,
          source_code: evidence.source.source_code,
          version_status: evidence.source.version_status,
          provenance: evidence.provenance,
        }}
      />
    </div>
  );
}

/** Drawer body for `GET /evidence/{handle}`: loading, error and tombstone states included. */
export function EvidenceDrawerBody({
  ws,
  handle,
  childId,
  hint,
  onSelectChild,
}: {
  ws: string;
  handle: string;
  childId: string | null;
  hint: SpanHint | null;
  onSelectChild?: (childId: string | null) => void;
}) {
  const query = useEvidencePassage(ws, handle, childId);
  if (query.isPending) return <LoadingRegion label="Loading evidence passage" lines={6} />;
  if (query.isError) return <PassageError error={query.error} handle={handle} onRetry={() => void query.refetch()} />;
  const evidence = query.data;
  return (
    <div className="ms-fade-in">
      <EvidencePassageView ws={ws} evidence={evidence} span={pickSpan(evidence, childId, hint)} onSelectChild={onSelectChild} />
    </div>
  );
}

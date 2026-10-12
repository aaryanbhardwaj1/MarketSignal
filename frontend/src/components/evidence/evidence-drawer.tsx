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
import { errorMessage, isTabularSource, sourceClass, sourceType } from "@/lib/labels";
import { Badge } from "../ui/badge";
import { RowFields } from "../ui/row-fields";
import { Callout } from "../ui/callout";
import { DevDetails, Disclosure } from "../ui/disclosure";
import { ErrorState, LoadingRegion } from "../ui/states";
import { ChildSpanList } from "./child-span-list";
import { ContextExcerpts } from "./context-excerpts";
import { HighlightedText } from "./highlighted-text";
import { VersionNotice } from "./version-notice";

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

function SourceSummary({ evidence }: { evidence: Evidence }) {
  const s = evidence.source;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-secondary">
      <Badge tone="neutral">{sourceClass(s.source_class).known ? sourceClass(s.source_class).label : "Source"}</Badge>
      {sourceType(s.source_type).known && <span>{sourceType(s.source_type).label}</span>}
      {!s.is_latest && <span>Earlier version of this source</span>}
    </div>
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
  return (
    <div className="flex flex-col gap-5">
      <SourceSummary evidence={evidence} />
      <VersionNotice ws={ws} handle={evidence.handle} source={evidence.source} />

      <section aria-labelledby="evidence-passage-label" className="flex flex-col gap-2">
        <div>
          <h3 id="evidence-passage-label" className="text-base font-semibold text-primary">
            {businessLocator(evidence.locator_label) || "Passage"}
          </h3>
          {headings.length > 0 && <p className="text-sm text-muted">{headings.join(" / ")}</p>}
        </div>
        <PassageBody evidence={evidence} span={span} />
      </section>

      <ContextExcerpts previous={evidence.context.previous_excerpt} next={evidence.context.next_excerpt} />

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
    <div className="flex flex-col gap-5">
      <EvidencePassageView ws={ws} evidence={evidence} span={pickSpan(evidence, childId, hint)} onSelectChild={onSelectChild} />
      <p className="border-t border-border pt-3 text-sm">
        <Link
          href={`/w/${encodeURIComponent(ws)}/evidence/sources/${encodeURIComponent(evidence.source.source_id)}`}
          className="font-medium text-accent-text hover:underline"
        >
          View source in Evidence Library
        </Link>
      </p>
    </div>
  );
}

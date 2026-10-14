"use client";

import { useQuery } from "@tanstack/react-query";
import { getSource } from "@/lib/api/endpoints";
import { isNotFoundError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/query-keys";
import type { SourceDetail, SourceVersion } from "@/lib/api/types";
import { formatDate, formatNumber, humanize } from "@/lib/format";

function confidentialityLabel(value: string): string {
  const text = humanize(value);
  return text.charAt(0).toUpperCase() + text.slice(1);
}
import { sourceClass, sourceType } from "@/lib/labels";
import { versionHistory, type VersionHistoryEntry } from "@/lib/library-filters";
import { isNonTerminalStatus, libraryStatusLabel, versionStatusLabel } from "@/lib/status";
import { LinkButton } from "../ui/button";
import { Callout } from "../ui/callout";
import { DevDetails } from "../ui/disclosure";
import { Card } from "../ui/card";
import { KeyValueList } from "../ui/key-value";
import { useDocumentTitle } from "@/lib/use-document-title";
import { SourceCitations } from "./source-citations";
import { PageContainer } from "../ui/page-container";
import { PageHeader } from "../ui/page-header";
import { Section } from "../ui/section";
import { EmptyState, ErrorState, LoadingRegion } from "../ui/states";
import { StatusIndicator } from "../ui/status-indicator";
import { evidenceLibraryHref } from "@/lib/routes";

const POLL_INTERVAL_MS = 3_000;

function countText(n: number | null): string {
  return n == null ? "Not yet available" : formatNumber(n);
}

function VersionHistory({ detail }: { detail: SourceDetail }) {
  const entries = versionHistory(detail);
  return (
    <Card padding="none">
    <ol aria-label="Version history" className="divide-y divide-border">
      {entries.map((entry) => {
        const status = entry.isCurrent
          ? versionStatusLabel(detail.versions.find((v) => v.version === entry.version)?.status)
          : libraryStatusLabel(entry.bucket);
        return (
          <li key={entry.version} className="grid grid-cols-[5rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3">
            <span className="text-base font-semibold tabular-nums text-primary">Version {entry.version}</span>
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-secondary">
              <StatusIndicator tone={status.tone} label={entry.isCurrent ? `Current · ${status.label}` : status.label} />
              {entry.date && <span>{entry.bucket === "ready" || entry.bucket === "superseded" ? "Ready" : "Added"} {formatDate(entry.date)}</span>}
            </span>
            <span className="text-right text-sm tabular-nums text-muted">
              {entry.passages != null ? `${formatNumber(entry.passages)} passages` : ""}
            </span>
          </li>
        );
      })}
    </ol>
    </Card>
  );
}

function technicalDetails(detail: SourceDetail): unknown {
  return {
    source_id: detail.source_id,
    source_code: detail.source_code,
    current_version_id: detail.current_version_id,
    indexed_segments: versionHistory(detail).find((e) => e.isCurrent)?.segments ?? null,
    versions: detail.versions.map((v) => ({
      version: v.version,
      version_id: v.version_id,
      status: v.status,
      original_filename: v.original_filename,
      byte_size: v.byte_size,
      embedding_model: v.embedding_model,
      attempts: v.attempts,
      error_code: v.error_code,
      error_detail: v.error_detail,
      warnings: v.warnings,
      health: v.health,
      timings: v.timings,
    })),
  };
}

function SourceStatusCallouts({ deleted, failed, processing }: { deleted: boolean; failed: boolean; processing: boolean }) {
  return (
    <>
      {deleted && (
        <div className="mt-6">
          <Callout tone="neutral" title="This source was removed from the library">
            Passages from it can no longer be cited. Earlier answers that cited it show it as removed.
          </Callout>
        </div>
      )}
      {!deleted && failed && (
        <div className="mt-6">
          <Callout tone="danger" title="The latest version could not be processed">
            It cannot be cited until it is processed successfully. The cause is recorded in Technical details.
          </Callout>
        </div>
      )}
      {!deleted && processing && (
        <div className="mt-6">
          <Callout tone="info" title="This source is still being processed">
            Its passages become searchable and citable once processing finishes. This page refreshes automatically.
          </Callout>
        </div>
      )}
    </>
  );
}

function AboutSource({ detail, current, currentVersion }: { detail: SourceDetail; current: VersionHistoryEntry | null; currentVersion: SourceVersion | null }) {
  return (
    <Section title="About this source">
      <Card padding="sm">
        <KeyValueList
          columns={2}
          items={[
            { label: "Category", value: currentVersion ? sourceClass(currentVersion.source_class).label : "-" },
            { label: "Type", value: sourceType(detail.source_type).label },
            { label: "Confidentiality", value: currentVersion ? confidentialityLabel(currentVersion.confidentiality) : "-" },
            { label: "Current version", value: current ? `Version ${current.version} of ${detail.versions.length}` : "-" },
            { label: "Evidence passages", value: countText(current?.passages ?? null) },
            { label: "Last updated", value: current?.date ? formatDate(current.date) : "-" },
          ]}
        />
      </Card>
    </Section>
  );
}

/** One source in the Evidence Library: what it is, where the brief cites it, and its versions. */
export function SourcePage({ ws, sourceId }: { ws: string; sourceId: string }) {
  const query = useQuery({
    queryKey: queryKeys.source(ws, sourceId),
    queryFn: ({ signal }) => getSource(ws, sourceId, signal),
    refetchInterval: (q) => (q.state.data?.versions.some((v) => isNonTerminalStatus(v.status)) ? POLL_INTERVAL_MS : false),
  });
  useDocumentTitle(query.data?.title, "Evidence Library");
  const crumbs = [{ label: "Evidence Library", href: evidenceLibraryHref(ws) }];
  if (query.isPending) {
    return (
      <PageContainer width="content">
        <PageHeader title="Source" breadcrumb={crumbs} />
        <div className="mt-6">
          <LoadingRegion label="Loading source" lines={8} />
        </div>
      </PageContainer>
    );
  }

  if (query.isError) {
    const notFound = isNotFoundError(query.error);
    return (
      <PageContainer width="content">
        <PageHeader title={notFound ? "Source not found" : "Source"} breadcrumb={crumbs} />
        <div className="mt-6">
          {notFound ? (
            <EmptyState
              title="This source is not in the library"
              description="The link may be out of date, or the source belongs to another workspace."
              action={<LinkButton href={evidenceLibraryHref(ws)} variant="secondary">Back to the Evidence Library</LinkButton>}
            />
          ) : (
            <ErrorState
              title="The source could not be loaded"
              error={query.error}
              retry={() => void query.refetch()}
            />
          )}
        </div>
      </PageContainer>
    );
  }

  const detail = query.data;
  const history = versionHistory(detail);
  const current = history.find((e) => e.isCurrent) ?? history[0] ?? null;
  const currentVersion = detail.versions.find((v) => v.version === current?.version) ?? null;
  const processing = currentVersion ? isNonTerminalStatus(currentVersion.status) : !detail.deleted;
  const status = detail.deleted ? libraryStatusLabel("removed") : versionStatusLabel(currentVersion?.status);

  return (
    <PageContainer width="content">
      <PageHeader
        breadcrumb={crumbs}
        title={detail.title}
        description={[
          currentVersion ? sourceClass(currentVersion.source_class).label : null,
          sourceType(detail.source_type).label,
          currentVersion ? confidentialityLabel(currentVersion.confidentiality) : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        meta={<StatusIndicator tone={processing ? "info" : status.tone} label={processing ? "Processing" : status.label} />}
      />

      <div className="mt-2 flex flex-col">
        <SourceStatusCallouts deleted={detail.deleted} failed={currentVersion?.status === "failed"} processing={!detail.deleted && processing} />
        <AboutSource detail={detail} current={current} currentVersion={currentVersion} />

        <Section
          title="Cited in the analyst brief"
          description="Passages from this source that insights and growth opportunities rely on. Open a passage to read it in context."
        >
          <SourceCitations ws={ws} sourceCode={detail.source_code} />
        </Section>

        <Section
          title="Version history"
          description={
            detail.versions.length > 1
              ? "Answers cite the current version. Superseded versions are kept so earlier citations stay traceable."
              : undefined
          }
        >
          {detail.versions.length === 0 ? (
            <EmptyState title="No versions recorded yet" />
          ) : (
            <VersionHistory detail={detail} />
          )}
        </Section>

        <div className="mt-8">
          <DevDetails data={technicalDetails(detail)} summary="Technical details (ingestion health)" />
        </div>
      </div>
    </PageContainer>
  );
}

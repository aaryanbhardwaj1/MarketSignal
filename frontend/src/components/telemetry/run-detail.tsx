"use client";

import Link from "next/link";
import type { TelemetryRunDetail } from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import { useTelemetryRun } from "@/lib/api/hooks/telemetry";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { CopyButton } from "@/components/ui/copy-button";
import { DevDetails } from "@/components/ui/disclosure";
import { EmptyState, ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { formatDateTime, formatMs, formatNumber, formatUsd } from "@/lib/format";
import { degradationFlag, runMode, runStatus, terminationState, verificationDisposition } from "@/lib/labels";
import { rowTokens, shortId } from "@/lib/telemetry-view";
import { AnalyticsResults, ResearchCard, RouteCard, StageTiming, UsageCard } from "./run-sections";
import { RetrievalPanel, RunTimeline, ToolCalls, VerificationAttempts } from "./run-trace";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { StatTile } from "./stat-tile";

export const REASONING_NOTE = "Model reasoning is not recorded; only observable actions, timings and outcomes are.";

const telemetryHref = (ws: string): string => `/w/${encodeURIComponent(ws)}/dev/telemetry`;

function crumbs(ws: string) {
  return [{ label: "Telemetry", href: telemetryHref(ws) }];
}

function HeaderMeta({ run }: { run: TelemetryRunDetail["run"] }) {
  const mode = runMode(run.mode);
  const end = run.total_ms != null ? new Date(new Date(run.created_at).getTime() + run.total_ms).toISOString() : null;
  return (
    <>
      <span className="inline-flex items-center gap-1.5">
        <span className="font-mono text-xs text-secondary" title={run.id}>
          {shortId(run.id)}
        </span>
        <CopyButton value={run.id} label="Copy run id" />
      </span>
      <Badge tone="accent">{mode.known ? mode.label : run.mode}</Badge>
      <span>Started {formatDateTime(run.created_at)}</span>
      {end && <span>Ended {formatDateTime(end)}</span>}
    </>
  );
}

function OutcomeStrip({ run }: { run: TelemetryRunDetail["run"] }) {
  const term = run.termination_state ? terminationState(run.termination_state) : null;
  const status = runStatus(run.status);
  const disp = run.verification_disposition ? verificationDisposition(run.verification_disposition) : null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        className="col-span-2"
        label="Outcome"
        value={
          <StatusIndicator
            tone={(term ?? status).tone ?? "neutral"}
            label={term ? (term.known ? term.label : term.code) : status.known ? status.label : run.status}
            className="text-base"
          />
        }
        context={
          <span>
            Status {status.known ? status.label.toLowerCase() : run.status}
            {run.termination_state && run.termination_state !== run.status && <span className="block font-mono">{run.termination_state}</span>}
          </span>
        }
      />
      <StatTile label="Latency" value={formatMs(run.total_ms)} context="Run start to completion" />
      <StatTile label="Calls" value={`${run.model_calls == null ? "n/a" : formatNumber(run.model_calls)} / ${formatNumber(run.tool_calls)}`} context="Model calls / tool calls" />
      <StatTile label="Tokens" value={formatNumber(run.tokens_in + run.tokens_out)} context={rowTokens(run) ?? "No model tokens"} />
      <StatTile label="Estimated cost" value={formatUsd(run.est_cost_usd)} context="List prices, not billed" />
      <StatTile
        label="Evidence"
        value={`${formatNumber(run.cited_count)} cited`}
        context={`of ${formatNumber(run.evidence_count)} in the pack${run.result_count ? ` · ${formatNumber(run.result_count)} computed` : ""}`}
      />
      <StatTile
        label="Verification"
        value={<span className="text-base">{disp ? (disp.known ? disp.label : run.verification_disposition) : "Not recorded"}</span>}
        context={run.regenerated ? "Answer was regenerated" : "No regeneration"}
      />
    </div>
  );
}

function Flags({ flags }: { flags: string[] }) {
  if (flags.length === 0) return null;
  return (
    <Callout tone="warn" title="Degraded run">
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {flags.map((f) => {
          const h = degradationFlag(f);
          return (
            <li key={f}>
              <Badge tone="warn" title={f}>
                {h.known ? h.label : f}
              </Badge>
              <span className="ml-1 font-mono text-xs text-muted">{f}</span>
            </li>
          );
        })}
      </ul>
    </Callout>
  );
}

/** Pure view of one run's telemetry (rendered by `RunDetail` once loaded; also used in tests). */
export function RunDetailView({ ws, detail }: { ws: string; detail: TelemetryRunDetail }) {
  const { run } = detail;
  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumb={crumbs(ws)}
        title={<span className="line-clamp-3">{run.question || "Run without a recorded question"}</span>}
        description="Observable actions, timings and checks for one run."
        meta={<HeaderMeta run={run} />}
      />
      <div className="mt-6 flex flex-col gap-3">
        <OutcomeStrip run={run} />
        <Flags flags={run.flags} />
        <Callout tone="neutral" title="What is recorded">
          {REASONING_NOTE}
        </Callout>
      </div>
      <Section title="Routing and research" description="Why this mode was used and how the research phase ended.">
        <div className="grid gap-3 lg:grid-cols-2">
          <RouteCard route={run.route} />
          <ResearchCard detail={detail} />
        </div>
      </Section>
      <Section title="Stage timing" description="Sequential stages from persisted timings.">
        <StageTiming detail={detail} />
      </Section>
      <Section title="Timeline" description="Observable events in order, relative to run start. Streamed text is aggregated, never shown.">
        <RunTimeline detail={detail} />
      </Section>
      <Section title="Tool calls" description="Audited research steps with sanitized arguments.">
        <ToolCalls detail={detail} />
      </Section>
      <Section title="Verification" description="Citation and number checks per synthesis attempt. Rejected spans are never stored; only reasons are.">
        <VerificationAttempts detail={detail} />
      </Section>
      <Section title="Retrieval" description="Hybrid search trace: candidates per lane, sub-stage timings and top final passages.">
        <RetrievalPanel detail={detail} />
      </Section>
      <Section title="Usage and computed results">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <UsageCard detail={detail} />
          <div className="rounded-lg border border-border bg-surface px-4 py-3">
            <h3 className="text-base font-semibold text-primary">Computed results</h3>
            <p className="mb-3 text-xs text-muted">Deterministic analytics results this run used.</p>
            <AnalyticsResults ids={detail.analytics_result_ids} />
          </div>
        </div>
      </Section>
      <Section title="Raw details">
        <DevDetails summary="Raw details (sanitized JSON)" data={detail} />
      </Section>
    </PageContainer>
  );
}

export function RunDetail({ ws, runId }: { ws: string; runId: string }) {
  const query = useTelemetryRun(ws, runId);
  if (query.isPending) {
    return (
      <PageContainer width="wide">
        <PageHeader breadcrumb={crumbs(ws)} title="Run telemetry" description="Loading this run's observable actions and timings." />
        <div className="mt-6">
          <LoadingRegion label="Loading run telemetry">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} height="5rem" />
              ))}
            </div>
            <Skeleton height="14rem" className="mt-6" />
          </LoadingRegion>
        </div>
      </PageContainer>
    );
  }
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <PageContainer width="wide">
        <PageHeader breadcrumb={crumbs(ws)} title="Run telemetry" />
        <div className="mt-6">
          {notFound ? (
            <EmptyState
              title="Run not found"
              description="No run with this id exists in this workspace. It may belong to another workspace or have been removed."
              action={
                <Link href={telemetryHref(ws)} className="text-sm font-medium text-accent-text hover:underline">
                  Back to Telemetry
                </Link>
              }
            />
          ) : (
            <ErrorState
              title="Run telemetry could not be loaded"
              description="The telemetry service did not respond. Try again."
              retry={() => void query.refetch()}
            />
          )}
        </div>
      </PageContainer>
    );
  }
  return <RunDetailView ws={ws} detail={query.data} />;
}

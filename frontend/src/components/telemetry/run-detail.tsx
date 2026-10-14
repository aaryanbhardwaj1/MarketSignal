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
import { runMode, runStatus, terminationState, verificationDisposition } from "@/lib/labels";
import { rowTokens, shortId } from "@/lib/telemetry-view";
import { AnalyticsResults, ResearchCard, RouteCard, UsageCard } from "./run-sections";
import { RetrievalPanel, RunTimeline, ToolCalls, VerificationAttempts } from "./run-trace";
import { EyeOff } from "lucide-react";
import { Stat, StatRow } from "@/components/ui/stat";
import { Panel } from "./stat-tile";
import { ExecutionFlow, FlowGantt } from "./trace/execution-flow";
import { degradedInfo } from "./trace/run-flow";
import { telemetryHref } from "@/lib/routes";

export const REASONING_NOTE = "Model reasoning is not recorded; only observable actions, timings and outcomes are.";

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

function RunHeadline({ run }: { run: TelemetryRunDetail["run"] }) {
  const term = run.termination_state ? terminationState(run.termination_state) : null;
  const status = runStatus(run.status);
  const outcome = term ?? status;
  const disp = run.verification_disposition ? verificationDisposition(run.verification_disposition) : null;
  return (
    <StatRow className="rounded-lg border border-border bg-surface px-4 py-3">
      <Stat
        size="sm"
        label="Outcome"
        tone={outcome.tone ?? "neutral"}
        value={<span className="text-base">{outcome.known ? outcome.label : outcome.code || run.status}</span>}
        sub={
          // The recorded code adds information only when it is not just the label in snake_case.
          run.termination_state && run.termination_state !== outcome.label.toLowerCase().replaceAll(" ", "_") ? (
            <span className="font-mono text-xs">{run.termination_state}</span>
          ) : undefined
        }
      />
      <Stat size="sm" label="Total time" value={formatMs(run.total_ms)} />
      <Stat
        size="sm"
        label="Model / tool calls"
        value={`${run.model_calls == null ? "n/a" : formatNumber(run.model_calls)} / ${formatNumber(run.tool_calls)}`}
      />
      <Stat size="sm" label="Tokens" value={formatNumber(run.tokens_in + run.tokens_out)} sub={rowTokens(run) ?? "No model tokens"} />
      <Stat size="sm" label="Est. cost (estimate)" value={formatUsd(run.est_cost_usd)} sub="List prices, not billed" />
      <Stat
        size="sm"
        label="Verification"
        tone={disp?.tone}
        value={<span className="text-base">{disp ? (disp.known ? disp.label : run.verification_disposition) : "Not recorded"}</span>}
        sub={run.regenerated ? "Answer was regenerated" : undefined}
      />
    </StatRow>
  );
}

/** "Degraded run" callout: termination state and flags, each with its plain-language reason. */
function DegradedCallout({ detail }: { detail: TelemetryRunDetail }) {
  const info = degradedInfo(detail);
  if (!info.degraded) return null;
  return (
    <Callout tone="warn" title="Degraded run">
      <ul className="mt-1 flex flex-col gap-1.5">
        {info.reasons.map((r) => (
          <li key={r.code} className="text-sm">
            <span className="font-medium text-primary">{r.label}</span>
            <span className="ml-1.5 font-mono text-xs text-muted">{r.code}</span>
            {r.description && <span className="block text-secondary">{r.description}</span>}
          </li>
        ))}
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
        <RunHeadline run={run} />
        <DegradedCallout detail={detail} />
        <p className="flex items-center gap-1.5 text-xs text-muted">
          <EyeOff aria-hidden className="size-3.5" />
          {REASONING_NOTE}
        </p>
      </div>
      <Section title="Execution flow" description="Stages this run recorded, in order. Stages that did not occur are omitted.">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <ExecutionFlow detail={detail} />
          <div className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start">
            <h3 className="text-sm font-semibold text-primary">Where the time went</h3>
            <FlowGantt detail={detail} />
          </div>
        </div>
      </Section>
      <Section title="Routing and research" description="Why this mode was used and how the research phase ended.">
        <div className="grid gap-3 lg:grid-cols-2">
          <RouteCard route={run.route} />
          <ResearchCard detail={detail} />
        </div>
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
          <Panel title="Computed results" meta="Deterministic analytics results this run used">
            <AnalyticsResults ids={detail.analytics_result_ids} />
          </Panel>
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

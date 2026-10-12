"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { TelemetryRunRow, TelemetrySummary } from "@/lib/api/contracts";
import { useWorkspaceOverview } from "@/lib/api/hooks/core";
import { useTelemetryRuns, useTelemetrySummary } from "@/lib/api/hooks/telemetry";
import { Button } from "@/components/ui/button";
import { FilterBar, FilterSelect } from "@/components/ui/filter-bar";
import { Checkbox } from "@/components/ui/form-controls";
import { LoadMore } from "@/components/ui/load-more";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import { formatNumber } from "@/lib/format";
import { runStatus, terminationState, verificationDisposition } from "@/lib/labels";
import {
  DEFAULT_VIEW,
  WINDOW_OPTIONS,
  parseViewState,
  runFilters,
  serializeViewState,
  summaryFilters,
  windowSince,
  type TelemetryViewState,
  type TelemetryWindow,
} from "@/lib/telemetry-view";
import { RunsTable } from "./runs-table";
import { Auditability, CostNote, CoverageNote, RetrievalSummary, StageLatencyTable, SummaryMetrics, ToolTable } from "./summary-panels";

function useViewState(): [TelemetryViewState, (patch: Partial<TelemetryViewState>) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const state = useMemo(() => parseViewState(params), [params]);
  const update = useCallback(
    (patch: Partial<TelemetryViewState>) => {
      const qs = serializeViewState({ ...state, ...patch });
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [state, router, pathname],
  );
  return [state, update];
}

function HeaderControls({
  state,
  update,
  excluded,
}: {
  state: TelemetryViewState;
  update: (patch: Partial<TelemetryViewState>) => void;
  excluded: number | null;
}) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <FilterSelect
        id="telemetry-window"
        label="Window"
        value={state.window}
        options={WINDOW_OPTIONS}
        onChange={(v) => update({ window: v as TelemetryWindow })}
      />
      <div className="flex flex-col gap-1 pb-1.5">
        <Checkbox
          id="telemetry-include-test"
          label="Include test-harness runs"
          checked={state.includeTestRuns}
          onChange={(e) => update({ includeTestRuns: e.target.checked })}
        />
        <span className="pl-6 text-xs text-muted">
          {state.includeTestRuns
            ? "Test-harness runs are included"
            : excluded == null
              ? "Excluded by default"
              : `${formatNumber(excluded)} test-harness runs excluded`}
        </span>
      </div>
    </div>
  );
}

function outcomeOptions(summary: TelemetrySummary | undefined) {
  const status = Object.keys(summary?.runs.by_status ?? {}).map((code) => ({ value: `status:${code}`, label: `Status: ${runStatus(code).known ? runStatus(code).label : code}` }));
  const term = Object.keys(summary?.runs.by_termination_state ?? {}).map((code) => ({
    value: `term:${code}`,
    label: `Ended: ${terminationState(code).known ? terminationState(code).label : code}`,
  }));
  return [{ value: "", label: "All outcomes" }, ...status, ...term];
}

function dispositionOptions(summary: TelemetrySummary | undefined) {
  const codes = Array.from(new Set((summary?.verification.dispositions ?? []).map((d) => d.disposition)));
  return [{ value: "", label: "Any verification" }, ...codes.map((c) => ({ value: c, label: verificationDisposition(c).label }))];
}

function RunsSection({ ws, state, update, since, summary }: { ws: string; state: TelemetryViewState; update: (p: Partial<TelemetryViewState>) => void; since: string | undefined; summary: TelemetrySummary | undefined }) {
  const router = useRouter();
  const runs = useTelemetryRuns(ws, runFilters(state, since));
  const rows = useMemo(() => runs.data?.pages.flatMap((p) => p.items) ?? [], [runs.data]);
  const filtered = state.mode || state.outcome || state.degraded || state.disposition;
  const open = (row: TelemetryRunRow) => router.push(`/w/${encodeURIComponent(ws)}/dev/telemetry/runs/${encodeURIComponent(row.id)}`);
  return (
    <Section title="Runs" description="Every persisted run in the window, newest first. Select a row for its timeline, tool calls and checks.">
      <div className="mb-3">
        <FilterBar onReset={filtered ? () => update({ mode: "", outcome: "", degraded: "", disposition: "" }) : undefined}>
          <FilterSelect
            id="runs-mode"
            label="Mode"
            value={state.mode}
            options={[
              { value: "", label: "All modes" },
              { value: "standard", label: "Standard" },
              { value: "research", label: "Research" },
            ]}
            onChange={(v) => update({ mode: v as TelemetryViewState["mode"] })}
          />
          <FilterSelect id="runs-outcome" label="Outcome" value={state.outcome} options={outcomeOptions(summary)} onChange={(v) => update({ outcome: v })} />
          <FilterSelect
            id="runs-degraded"
            label="Degraded"
            value={state.degraded}
            options={[
              { value: "", label: "Any" },
              { value: "yes", label: "Degraded only" },
              { value: "no", label: "Not degraded" },
            ]}
            onChange={(v) => update({ degraded: v as TelemetryViewState["degraded"] })}
          />
          <FilterSelect
            id="runs-disposition"
            label="Verification"
            value={state.disposition}
            options={dispositionOptions(summary)}
            onChange={(v) => update({ disposition: v as TelemetryViewState["disposition"] })}
          />
        </FilterBar>
      </div>
      {runs.isPending ? (
        <LoadingRegion label="Loading runs">
          <Skeleton height="16rem" />
        </LoadingRegion>
      ) : runs.isError ? (
        <ErrorState title="Runs could not be loaded" description="The telemetry service did not respond. Try again." retry={() => void runs.refetch()} />
      ) : (
        <>
          <RunsTable rows={rows} onOpen={open} />
          <p className="mt-2 text-xs text-muted">
            Showing {formatNumber(rows.length)} runs. Tokens are input / output across synthesis and research; estimated cost uses list prices and is not a billed amount.
          </p>
          <LoadMore hasMore={Boolean(runs.hasNextPage)} loading={runs.isFetchingNextPage} onLoadMore={() => void runs.fetchNextPage()} />
        </>
      )}
    </Section>
  );
}

function SummaryBody({ summary }: { summary: TelemetrySummary }) {
  return (
    <>
      <Section title="Summary" description="Volume, latency, usage and quality rates for runs in the window.">
        <SummaryMetrics summary={summary} />
        <CostNote cost={summary.cost} />
        <div className="mt-3">
          <CoverageNote summary={summary} />
        </div>
      </Section>
      <Section title="Stage latency" description="Where run time goes. Stages a run did not perform are not counted.">
        <StageLatencyTable summary={summary} />
      </Section>
      <Section title="Research tools" description="Audited tool calls made during research, by tool and outcome.">
        <ToolTable summary={summary} />
      </Section>
      <Section title="Retrieval" description="Hybrid search traces: candidates per lane and sub-stage timings.">
        <RetrievalSummary summary={summary} />
      </Section>
      <Section title="Auditability" description="Why runs were routed, how answers were checked, and what degraded.">
        <Auditability summary={summary} />
      </Section>
    </>
  );
}

export function TelemetryDashboard({ ws }: { ws: string }) {
  const [state, update] = useViewState();
  const since = useMemo(() => windowSince(state.window), [state.window]);
  const summary = useTelemetrySummary(ws, summaryFilters(state, since));
  const overview = useWorkspaceOverview(ws);
  const data = summary.data;
  const name = overview.data?.name ?? ws;
  return (
    <PageContainer width="wide">
      <PageHeader
        title="Telemetry"
        description="Observable runs for this workspace: latency, usage, estimated cost, routing and answer checks."
        meta={
          <>
            <span>{name}</span>
            <span aria-hidden>·</span>
            <span>Developer tools</span>
          </>
        }
        actions={<HeaderControls state={state} update={update} excluded={data && !state.includeTestRuns ? data.test_runs_excluded : null} />}
      />
      <div className="mt-6">
        {summary.isPending ? (
          <LoadingRegion label="Loading telemetry summary">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
              {Array.from({ length: 12 }, (_, i) => (
                <Skeleton key={i} height="5.5rem" />
              ))}
            </div>
          </LoadingRegion>
        ) : summary.isError ? (
          <ErrorState title="Telemetry could not be loaded" description="The telemetry service did not respond. Try again." retry={() => void summary.refetch()} />
        ) : data && data.runs.total === 0 ? (
          <EmptyState
            title="No runs in this window"
            description={
              state.includeTestRuns
                ? "No runs were recorded in this window. Choose a wider window."
                : `No runs were recorded in this window. Choose a wider window${data.test_runs_excluded ? `, or include the ${formatNumber(data.test_runs_excluded)} test-harness runs` : ""}.`
            }
            action={
              state.window !== DEFAULT_VIEW.window ? (
                <Button variant="secondary" size="sm" onClick={() => update({ window: "all" })}>
                  Show all time
                </Button>
              ) : undefined
            }
          />
        ) : data ? (
          <>
            <SummaryBody summary={data} />
            <RunsSection ws={ws} state={state} update={update} since={since} summary={data} />
          </>
        ) : null}
      </div>
    </PageContainer>
  );
}

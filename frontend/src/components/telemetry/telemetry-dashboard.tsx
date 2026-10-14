"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { TelemetryRunRow, TelemetrySummary, TelemetrySummaryWithOutcomes } from "@/lib/api/contracts";
import { useWorkspaceOverview } from "@/lib/api/hooks/core";
import { useTelemetryRuns, useTelemetrySeries, useTelemetrySummary } from "@/lib/api/hooks/telemetry";
import { Button } from "@/components/ui/button";
import { FilterBar, FilterSelect } from "@/components/ui/filter-bar";
import { Checkbox } from "@/components/ui/form-controls";
import { LoadMore } from "@/components/ui/load-more";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { formatNumber } from "@/lib/format";
import { runStatus, terminationState, verificationDisposition } from "@/lib/labels";
import {
  DEFAULT_VIEW,
  TELEMETRY_TABS,
  WINDOW_OPTIONS,
  parseTab,
  parseViewState,
  runFilters,
  serializeViewState,
  summaryFilters,
  windowSince,
  type TelemetryTab,
  type TelemetryViewState,
  type TelemetryWindow,
} from "@/lib/telemetry-view";
import { telemetryRunHref } from "@/lib/routes";
import { ServerLogViewer } from "@/components/telemetry/server-log/server-log-viewer";
import { ApiReadiness } from "./api-readiness";
import { RunsTable } from "./runs-table";
import { TelemetryOverview } from "./overview/telemetry-overview";

const TAB_PREFIX = "telemetry";
const SERIES_LIMIT = 2000;

export const RECORDED_NOTE =
  "Only observable actions are recorded: timings, token counts, tool calls and checks. Model reasoning is never recorded. Cost is an estimate at list prices, not a billed amount.";

type Update = (patch: Partial<TelemetryViewState>, tab?: TelemetryTab) => void;

function useViewState(): [TelemetryViewState, TelemetryTab, Update] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const state = useMemo(() => parseViewState(params), [params]);
  const tab = useMemo(() => parseTab(params), [params]);
  const update = useCallback<Update>(
    (patch, nextTab = tab) => {
      const qs = new URLSearchParams(serializeViewState({ ...state, ...patch }));
      if (nextTab !== "overview") qs.set("tab", nextTab);
      const s = qs.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [state, tab, router, pathname],
  );
  return [state, tab, update];
}

function HeaderControls({ state, update, excluded }: { state: TelemetryViewState; update: Update; excluded: number | null }) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <FilterSelect id="telemetry-window" label="Window" value={state.window} options={WINDOW_OPTIONS} onChange={(v) => update({ window: v as TelemetryWindow })} />
      <div className="flex flex-col gap-1 pb-1.5">
        <Checkbox
          id="telemetry-include-test"
          label="Include test-harness runs"
          checked={state.includeTestRuns}
          onChange={(e) => update({ includeTestRuns: e.target.checked })}
        />
        <span className="pl-6 text-xs text-muted tabular-nums">
          {state.includeTestRuns ? "Test-harness runs are included" : excluded == null ? "Excluded by default" : `${formatNumber(excluded)} test-harness runs excluded`}
        </span>
      </div>
    </div>
  );
}

function outcomeOptions(summary: TelemetrySummary | undefined) {
  const label = (h: { known: boolean; label: string }, code: string) => (h.known ? h.label : code);
  const status = Object.keys(summary?.runs.by_status ?? {}).map((code) => ({ value: `status:${code}`, label: `Status: ${label(runStatus(code), code)}` }));
  const term = Object.keys(summary?.runs.by_termination_state ?? {}).map((code) => ({ value: `term:${code}`, label: `Ended: ${label(terminationState(code), code)}` }));
  return [{ value: "", label: "All outcomes" }, ...status, ...term];
}

function dispositionOptions(summary: TelemetrySummary | undefined) {
  const codes = Array.from(new Set((summary?.verification.dispositions ?? []).map((d) => d.disposition)));
  return [{ value: "", label: "Any verification" }, ...codes.map((c) => ({ value: c, label: verificationDisposition(c).label }))];
}

function RunsFilters({ state, update, summary }: { state: TelemetryViewState; update: Update; summary: TelemetrySummary | undefined }) {
  const filtered = state.mode || state.outcome || state.degraded || state.disposition;
  return (
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
        id="runs-disposition"
        label="Verification"
        value={state.disposition}
        options={dispositionOptions(summary)}
        onChange={(v) => update({ disposition: v as TelemetryViewState["disposition"] })}
      />
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
    </FilterBar>
  );
}

function RunsExplorer({ ws, state, update, since, summary }: { ws: string; state: TelemetryViewState; update: Update; since: string | undefined; summary: TelemetrySummary | undefined }) {
  const router = useRouter();
  const runs = useTelemetryRuns(ws, runFilters(state, since));
  const rows = useMemo(() => runs.data?.pages.flatMap((p) => p.items) ?? [], [runs.data]);
  const runHref = (row: TelemetryRunRow) => telemetryRunHref(ws, row.id);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-secondary">Every persisted run in the window, newest first. Open a run for its timeline, tool calls and checks.</p>
      <RunsFilters state={state} update={update} summary={summary} />
      {runs.isPending ? (
        <LoadingRegion label="Loading runs">
          <Skeleton height="20rem" />
        </LoadingRegion>
      ) : runs.isError ? (
        <ErrorState title="Runs could not be loaded" description="The telemetry service did not respond. Try again." error={runs.error} retry={() => void runs.refetch()} />
      ) : (
        <>
          <RunsTable rows={rows} runHref={runHref} onOpen={(row) => router.push(runHref(row))} />
          <p className="text-xs text-muted tabular-nums">
            Showing {formatNumber(rows.length)}
            {summary && !state.mode && !state.outcome && !state.degraded && !state.disposition ? ` of ${formatNumber(summary.runs.total)}` : ""} runs. Cost is estimated from persisted usage at list prices.
          </p>
          <LoadMore hasMore={Boolean(runs.hasNextPage)} loading={runs.isFetchingNextPage} onLoadMore={() => void runs.fetchNextPage()} />
        </>
      )}
    </div>
  );
}

function OverviewTab({ ws, state, update, since, summary }: { ws: string; state: TelemetryViewState; update: Update; since: string | undefined; summary: ReturnType<typeof useTelemetrySummary> }) {
  const series = useTelemetrySeries(ws, { since, include_test_runs: state.includeTestRuns, limit: SERIES_LIMIT });
  const data: TelemetrySummaryWithOutcomes | undefined = summary.data;
  if (summary.isPending) {
    return (
      <LoadingRegion label="Loading telemetry summary">
        <Skeleton height="5rem" />
        <Skeleton height="16rem" />
      </LoadingRegion>
    );
  }
  if (summary.isError || !data) {
    return <ErrorState title="Telemetry could not be loaded" description="The telemetry service did not respond. Try again." error={summary.error} retry={() => void summary.refetch()} />;
  }
  if (data.runs.total === 0) {
    return (
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
    );
  }
  return (
    <TelemetryOverview
      summary={data}
      series={{ data: series.data, pending: series.isPending, error: series.isError ? series.error : null, retry: () => void series.refetch() }}
    />
  );
}

export function TelemetryDashboard({ ws }: { ws: string }) {
  const [state, tab, update] = useViewState();
  const since = useMemo(() => windowSince(state.window), [state.window]);
  const summary = useTelemetrySummary(ws, summaryFilters(state, since));
  const overview = useWorkspaceOverview(ws);
  const name = overview.data?.name ?? ws;
  const excluded = summary.data && !state.includeTestRuns ? summary.data.test_runs_excluded : null;
  return (
    <PageContainer width="wide">
      <PageHeader
        title="Telemetry"
        description="Operational record of every AI run: latency, tokens, tool use and verification — from persisted data."
        meta={
          <>
            <span>{name}</span>
            <span aria-hidden>·</span>
            <span>Developer tools</span>
            <span aria-hidden>·</span>
            <ApiReadiness />
          </>
        }
        actions={tab === "logs" ? undefined : <HeaderControls state={state} update={update} excluded={excluded} />}
        divider={false}
      />
      <p className="-mt-2 mb-4 max-w-reading text-xs text-muted">{RECORDED_NOTE}</p>
      <Tabs tabs={TELEMETRY_TABS} value={tab} onChange={(id) => update({}, id as TelemetryTab)} label="Telemetry views" idPrefix={TAB_PREFIX} />
      <TabPanel idPrefix={TAB_PREFIX} id={tab}>
        <div className="pt-4">
          {tab === "overview" && <OverviewTab ws={ws} state={state} update={update} since={since} summary={summary} />}
          {tab === "runs" && <RunsExplorer ws={ws} state={state} update={update} since={since} summary={summary.data} />}
          {tab === "logs" && <ServerLogViewer />}
        </div>
      </TabPanel>
    </PageContainer>
  );
}

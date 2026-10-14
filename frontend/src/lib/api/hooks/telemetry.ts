"use client";

/**
 * Run telemetry hooks (E10, developer tools). Owned by the telemetry workstream; telemetry
 * pages import these instead of calling endpoints directly. Shapes: `../contracts`.
 *
 * Test-harness runs are excluded unless `include_test_runs` is set; cost is an estimate from
 * persisted usage at list prices (`CostEstimate`).
 */

import {
  useInfiniteQuery,
  useQuery,
  type InfiniteData,
  type UseInfiniteQueryResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { apiGet } from "../client";
import type {
  Cursor,
  Disposition,
  Page,
  ServerLogParams,
  ServerLogResponse,
  TelemetryRunDetail,
  TelemetryRunRow,
  TelemetrySeries,
  TelemetrySummaryWithOutcomes,
} from "../contracts";

export type TelemetryMode = "standard" | "research";

/** Shared summary query: `since`/`until` are ISO 8601 timestamps with an offset. */
export interface TelemetrySummaryFilters {
  since?: string;
  until?: string;
  mode?: TelemetryMode;
  include_test_runs?: boolean;
}

export interface TelemetryRunFilters extends TelemetrySummaryFilters {
  status?: string;
  termination_state?: string;
  degraded?: boolean;
  model?: string;
  disposition?: Disposition;
  /** 1..100, server default 25. */
  limit?: number;
}

type Query = Record<string, string | number | undefined>;

const flag = (value: boolean | undefined): string | undefined =>
  value === undefined ? undefined : String(value);

function summaryQuery(filters: TelemetrySummaryFilters): Query {
  return {
    since: filters.since,
    until: filters.until,
    mode: filters.mode,
    include_test_runs: flag(filters.include_test_runs),
  };
}

function runsQuery(filters: TelemetryRunFilters, cursor: Cursor): Query {
  return {
    ...summaryQuery(filters),
    status: filters.status,
    termination_state: filters.termination_state,
    degraded: flag(filters.degraded),
    model: filters.model,
    disposition: filters.disposition,
    limit: filters.limit,
    cursor: cursor ?? undefined,
  };
}

/** Series filters: the summary window plus `limit` (1..2000, server default 500). */
export interface TelemetrySeriesFilters extends TelemetrySummaryFilters {
  limit?: number;
}

export function seriesQuery(filters: TelemetrySeriesFilters): Query {
  return { ...summaryQuery(filters), limit: filters.limit };
}

/** Query parameters for `GET /api/dev/logs` (unset values are omitted). */
export function serverLogQuery(params: ServerLogParams): Query {
  const q = params.q?.trim();
  return {
    level: params.level,
    kind: params.kind,
    method: params.method,
    status_class: params.status_class,
    route: params.route,
    q: q ? q : undefined,
    include_noise: flag(params.include_noise),
    after_seq: params.after_seq,
    limit: params.limit,
  };
}

const base = (ws: string): string => `/api/workspaces/${encodeURIComponent(ws)}/telemetry`;

export const telemetryKeys = {
  all: (ws: string) => ["workspace", ws, "telemetry"] as const,
  summary: (ws: string, filters: TelemetrySummaryFilters) =>
    ["workspace", ws, "telemetry", "summary", summaryQuery(filters)] as const,
  runs: (ws: string, filters: TelemetryRunFilters) =>
    ["workspace", ws, "telemetry", "runs", runsQuery(filters, null)] as const,
  run: (ws: string, runId: string) => ["workspace", ws, "telemetry", "run", runId] as const,
  series: (ws: string, filters: TelemetrySeriesFilters) =>
    ["workspace", ws, "telemetry", "series", seriesQuery(filters)] as const,
};

export const getTelemetrySummary = (
  ws: string,
  filters: TelemetrySummaryFilters = {},
  signal?: AbortSignal,
): Promise<TelemetrySummaryWithOutcomes> =>
  apiGet<TelemetrySummaryWithOutcomes>(`${base(ws)}/summary`, { query: summaryQuery(filters), signal });

export const getTelemetryRuns = (
  ws: string,
  filters: TelemetryRunFilters = {},
  cursor: Cursor = null,
  signal?: AbortSignal,
): Promise<Page<TelemetryRunRow>> =>
  apiGet<Page<TelemetryRunRow>>(`${base(ws)}/runs`, { query: runsQuery(filters, cursor), signal });

export const getTelemetryRun = (
  ws: string,
  runId: string,
  signal?: AbortSignal,
): Promise<TelemetryRunDetail> =>
  apiGet<TelemetryRunDetail>(`${base(ws)}/runs/${encodeURIComponent(runId)}`, { signal });

export function useTelemetrySummary(
  ws: string,
  filters: TelemetrySummaryFilters = {},
): UseQueryResult<TelemetrySummaryWithOutcomes> {
  return useQuery({
    queryKey: telemetryKeys.summary(ws, filters),
    queryFn: ({ signal }) => getTelemetrySummary(ws, filters, signal),
    enabled: Boolean(ws),
    staleTime: 30_000,
  });
}

/** Keyset-paginated runs, newest first; `fetchNextPage()` loads the next page ("Load more"). */
export function useTelemetryRuns(
  ws: string,
  filters: TelemetryRunFilters = {},
): UseInfiniteQueryResult<InfiniteData<Page<TelemetryRunRow>, Cursor>> {
  return useInfiniteQuery({
    queryKey: telemetryKeys.runs(ws, filters),
    queryFn: ({ pageParam, signal }) => getTelemetryRuns(ws, filters, pageParam, signal),
    initialPageParam: null as Cursor,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: Boolean(ws),
    staleTime: 30_000,
  });
}

/** One run's telemetry detail; a 404 (`RUN_NOT_FOUND`) surfaces as the query error. */
export function useTelemetryRun(
  ws: string,
  runId: string | null | undefined,
): UseQueryResult<TelemetryRunDetail> {
  return useQuery({
    queryKey: telemetryKeys.run(ws, runId ?? ""),
    queryFn: ({ signal }) => getTelemetryRun(ws, runId as string, signal),
    enabled: Boolean(ws && runId),
    staleTime: 60_000,
  });
}

// --- E12: telemetry series + server log --------------------------------------------------------

export const serverLogKeys = {
  all: ["dev", "server-logs"] as const,
  list: (params: ServerLogParams) => ["dev", "server-logs", serverLogQuery(params)] as const,
};

export const getTelemetrySeries = (
  ws: string,
  filters: TelemetrySeriesFilters = {},
  signal?: AbortSignal,
): Promise<TelemetrySeries> =>
  apiGet<TelemetrySeries>(`${base(ws)}/series`, { query: seriesQuery(filters), signal });

export const getServerLogs = (
  params: ServerLogParams = {},
  signal?: AbortSignal,
): Promise<ServerLogResponse> =>
  apiGet<ServerLogResponse>("/api/dev/logs", { query: serverLogQuery(params), signal });

/** Per-run points for the Telemetry charts, oldest first; nulls are "not recorded". */
export function useTelemetrySeries(
  ws: string,
  filters: TelemetrySeriesFilters = {},
): UseQueryResult<TelemetrySeries> {
  return useQuery({
    queryKey: telemetryKeys.series(ws, filters),
    queryFn: ({ signal }) => getTelemetrySeries(ws, filters, signal),
    enabled: Boolean(ws),
    staleTime: 30_000,
  });
}

export interface ServerLogOptions {
  /** Poll interval in ms; omitted, 0 or false: no polling. Paused while the tab is hidden. */
  pollMs?: number | false;
  enabled?: boolean;
}

/** The API process's recent log entries (dev only; a 404 means the endpoint is not mounted). */
export function useServerLogs(
  params: ServerLogParams = {},
  { pollMs, enabled = true }: ServerLogOptions = {},
): UseQueryResult<ServerLogResponse> {
  return useQuery({
    queryKey: serverLogKeys.list(params),
    queryFn: ({ signal }) => getServerLogs(params, signal),
    enabled,
    staleTime: 0,
    refetchInterval: pollMs ? pollMs : false,
    refetchIntervalInBackground: false,
  });
}

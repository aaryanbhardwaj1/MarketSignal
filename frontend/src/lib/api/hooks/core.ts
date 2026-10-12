"use client";

/**
 * Core product hooks (final phase): capabilities, workspaces, workspace overview, the
 * conversation list, saved runs and their verification, and analytics datasets/results. Owned by
 * the core-API workstream; pages import these instead of calling endpoints directly.
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
  AnalyticsResultSummary,
  Capabilities,
  ConversationSummary,
  Cursor,
  DatasetInfo,
  DatasetList,
  Page,
  RunRecord,
  RunVerification,
  WorkspaceOverview,
} from "../contracts";
import { listWorkspaces } from "../endpoints";
import type { Workspace } from "../types";

export interface ConversationFilters {
  featured?: boolean;
  q?: string;
  includeTestRuns?: boolean;
  limit?: number;
}

export interface AnalyticsResultFilters {
  tool?: AnalyticsResultSummary["tool"];
  runId?: string;
  includeTestRuns?: boolean;
  limit?: number;
}

const wsPath = (ws: string): string => `/api/workspaces/${encodeURIComponent(ws)}`;
const flag = (value: boolean | undefined): string | undefined =>
  value === undefined ? undefined : String(value);

export const coreKeys = {
  capabilities: ["capabilities"] as const,
  workspaces: ["workspaces"] as const,
  overview: (ws: string) => ["workspace", ws, "overview"] as const,
  conversations: (ws: string, filters: ConversationFilters) =>
    ["workspace", ws, "conversations", "list", filters] as const,
  run: (ws: string, runId: string) => ["workspace", ws, "runs", runId] as const,
  verification: (ws: string, runId: string) => ["workspace", ws, "runs", runId, "verification"] as const,
  datasets: (ws: string) => ["workspace", ws, "analytics", "datasets"] as const,
  dataset: (ws: string, datasetId: string) => ["workspace", ws, "analytics", "datasets", datasetId] as const,
  analyticsResults: (ws: string, filters: AnalyticsResultFilters) =>
    ["workspace", ws, "analytics", "results", filters] as const,
};

export const getCapabilities = (signal?: AbortSignal): Promise<Capabilities> =>
  apiGet<Capabilities>("/api/capabilities", { signal });

export const getWorkspaceOverview = (ws: string, signal?: AbortSignal): Promise<WorkspaceOverview> =>
  apiGet<WorkspaceOverview>(wsPath(ws), { signal });

export const getConversations = (
  ws: string,
  filters: ConversationFilters = {},
  cursor: Cursor = null,
  signal?: AbortSignal,
): Promise<Page<ConversationSummary>> =>
  apiGet<Page<ConversationSummary>>(`${wsPath(ws)}/conversations`, {
    query: {
      limit: filters.limit,
      cursor,
      q: filters.q?.trim() || undefined,
      featured: flag(filters.featured),
      include_test_runs: flag(filters.includeTestRuns),
    },
    signal,
  });

export const getRun = (ws: string, runId: string, signal?: AbortSignal): Promise<RunRecord> =>
  apiGet<RunRecord>(`${wsPath(ws)}/runs/${encodeURIComponent(runId)}`, { signal });

export const getRunVerification = (
  ws: string,
  runId: string,
  signal?: AbortSignal,
): Promise<RunVerification> =>
  apiGet<RunVerification>(`${wsPath(ws)}/runs/${encodeURIComponent(runId)}/verification`, { signal });

export const getDatasets = (ws: string, signal?: AbortSignal): Promise<DatasetList> =>
  apiGet<DatasetList>(`${wsPath(ws)}/analytics/datasets`, { signal });

/** One dataset with its columns; `datasetId` looks like `SURVEY-2026:1`. */
export const getDataset = (ws: string, datasetId: string, signal?: AbortSignal): Promise<DatasetInfo> =>
  apiGet<DatasetInfo>(`${wsPath(ws)}/analytics/datasets/${encodeURIComponent(datasetId)}`, { signal });

export const getAnalyticsResults = (
  ws: string,
  filters: AnalyticsResultFilters = {},
  cursor: Cursor = null,
  signal?: AbortSignal,
): Promise<Page<AnalyticsResultSummary>> =>
  apiGet<Page<AnalyticsResultSummary>>(`${wsPath(ws)}/analytics/results`, {
    query: {
      limit: filters.limit,
      cursor,
      tool: filters.tool,
      run_id: filters.runId,
      include_test_runs: flag(filters.includeTestRuns),
    },
    signal,
  });

/** Whether live answer generation is available. Treated as unavailable until known. */
export function useCapabilities(): UseQueryResult<Capabilities> {
  return useQuery({
    queryKey: coreKeys.capabilities,
    queryFn: ({ signal }) => getCapabilities(signal),
    staleTime: 60_000,
  });
}

export function useWorkspaces(): UseQueryResult<Workspace[]> {
  return useQuery({ queryKey: coreKeys.workspaces, queryFn: ({ signal }) => listWorkspaces(signal) });
}

export function useWorkspaceOverview(ws: string): UseQueryResult<WorkspaceOverview> {
  return useQuery({
    queryKey: coreKeys.overview(ws),
    queryFn: ({ signal }) => getWorkspaceOverview(ws, signal),
    enabled: Boolean(ws),
  });
}

/**
 * Conversations, newest activity first, keyset-paginated (`fetchNextPage()` loads more).
 * `featured: true` returns the curated demo list in its display order as a single page.
 */
export function useConversations(
  ws: string,
  filters: ConversationFilters = {},
): UseInfiniteQueryResult<InfiniteData<Page<ConversationSummary>, Cursor>> {
  return useInfiniteQuery({
    queryKey: coreKeys.conversations(ws, filters),
    queryFn: ({ pageParam, signal }) => getConversations(ws, filters, pageParam, signal),
    initialPageParam: null as Cursor,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: Boolean(ws),
    staleTime: 30_000,
  });
}

/** A saved run (`GET /runs/{id}`); a 404 (`RUN_NOT_FOUND`) surfaces as the query error. */
export function useRun(ws: string, runId: string | null | undefined): UseQueryResult<RunRecord> {
  return useQuery({
    queryKey: coreKeys.run(ws, runId ?? ""),
    queryFn: ({ signal }) => getRun(ws, runId as string, signal),
    enabled: Boolean(ws && runId),
    staleTime: 60_000,
  });
}

/** Per-attempt verification summary of a run (never includes rejected answer text). */
export function useRunVerification(
  ws: string,
  runId: string | null | undefined,
): UseQueryResult<RunVerification> {
  return useQuery({
    queryKey: coreKeys.verification(ws, runId ?? ""),
    queryFn: ({ signal }) => getRunVerification(ws, runId as string, signal),
    enabled: Boolean(ws && runId),
    staleTime: 60_000,
  });
}

export function useDatasets(ws: string): UseQueryResult<DatasetList> {
  return useQuery({
    queryKey: coreKeys.datasets(ws),
    queryFn: ({ signal }) => getDatasets(ws, signal),
    enabled: Boolean(ws),
    staleTime: 60_000,
  });
}

/** One dataset with columns; a 404 (`DATASET_NOT_FOUND`) surfaces as the query error. */
export function useDataset(ws: string, datasetId: string | null | undefined): UseQueryResult<DatasetInfo> {
  return useQuery({
    queryKey: coreKeys.dataset(ws, datasetId ?? ""),
    queryFn: ({ signal }) => getDataset(ws, datasetId as string, signal),
    enabled: Boolean(ws && datasetId),
    staleTime: 60_000,
  });
}

/** Persisted computed results, newest first, keyset-paginated. */
export function useAnalyticsResults(
  ws: string,
  filters: AnalyticsResultFilters = {},
): UseInfiniteQueryResult<InfiniteData<Page<AnalyticsResultSummary>, Cursor>> {
  return useInfiniteQuery({
    queryKey: coreKeys.analyticsResults(ws, filters),
    queryFn: ({ pageParam, signal }) => getAnalyticsResults(ws, filters, pageParam, signal),
    initialPageParam: null as Cursor,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: Boolean(ws),
    staleTime: 30_000,
  });
}

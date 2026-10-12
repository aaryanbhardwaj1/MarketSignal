"use client";

/**
 * Curated analyst brief hooks (final phase): key signals and growth opportunities
 * (`GET /insights`) and the named analyses (`GET /analytics/analyses[/{id}]`). The backend
 * re-verifies every quote and recomputes every number on request, so items can come back with
 * numbers withheld (`value: null`) or evidence marked stale/withdrawn; pages render those states
 * rather than treating them as errors. A workspace without a brief returns
 * `fixture_version: null` and empty lists.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "../client";
import type { AnalysesResponse, Analysis, InsightsBrief } from "../contracts";

const wsPath = (ws: string): string => `/api/workspaces/${encodeURIComponent(ws)}`;
const STALE_MS = 60_000;

export const insightsKeys = {
  brief: (ws: string) => ["workspace", ws, "insights"] as const,
  analyses: (ws: string) => ["workspace", ws, "analytics", "analyses"] as const,
  analysis: (ws: string, id: string) => ["workspace", ws, "analytics", "analyses", id] as const,
};

export const getInsights = (ws: string, signal?: AbortSignal): Promise<InsightsBrief> =>
  apiGet<InsightsBrief>(`${wsPath(ws)}/insights`, { signal });

export const getAnalyses = (ws: string, signal?: AbortSignal): Promise<AnalysesResponse> =>
  apiGet<AnalysesResponse>(`${wsPath(ws)}/analytics/analyses`, { signal });

/** One named analysis; an unknown id is a 404 (`ANALYSIS_NOT_FOUND`). */
export const getAnalysis = (ws: string, id: string, signal?: AbortSignal): Promise<Analysis> =>
  apiGet<Analysis>(`${wsPath(ws)}/analytics/analyses/${encodeURIComponent(id)}`, { signal });

export function useInsights(ws: string): UseQueryResult<InsightsBrief> {
  return useQuery({
    queryKey: insightsKeys.brief(ws),
    queryFn: ({ signal }) => getInsights(ws, signal),
    enabled: Boolean(ws),
    staleTime: STALE_MS,
  });
}

export function useAnalyses(ws: string): UseQueryResult<AnalysesResponse> {
  return useQuery({
    queryKey: insightsKeys.analyses(ws),
    queryFn: ({ signal }) => getAnalyses(ws, signal),
    enabled: Boolean(ws),
    staleTime: STALE_MS,
  });
}

/** A 404 (`ANALYSIS_NOT_FOUND`) surfaces as the query error. */
export function useAnalysis(ws: string, id: string | null | undefined): UseQueryResult<Analysis> {
  return useQuery({
    queryKey: insightsKeys.analysis(ws, id ?? ""),
    queryFn: ({ signal }) => getAnalysis(ws, id as string, signal),
    enabled: Boolean(ws && id),
    staleTime: STALE_MS,
  });
}

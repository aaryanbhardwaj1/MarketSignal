"use client";

/**
 * Core product hooks (final phase): capabilities, workspaces and workspace overview. Owned by
 * the core-API workstream; pages import these instead of calling endpoints directly.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "../client";
import type { Capabilities, WorkspaceOverview } from "../contracts";
import { listWorkspaces } from "../endpoints";
import type { Workspace } from "../types";

export const coreKeys = {
  capabilities: ["capabilities"] as const,
  workspaces: ["workspaces"] as const,
  overview: (ws: string) => ["workspace", ws, "overview"] as const,
};

export const getCapabilities = (signal?: AbortSignal): Promise<Capabilities> =>
  apiGet<Capabilities>("/api/capabilities", { signal });

export const getWorkspaceOverview = (ws: string, signal?: AbortSignal): Promise<WorkspaceOverview> =>
  apiGet<WorkspaceOverview>(`/api/workspaces/${encodeURIComponent(ws)}`, { signal });

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
  });
}

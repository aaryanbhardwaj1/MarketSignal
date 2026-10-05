import type { SearchMode } from "./types";

export const queryKeys = {
  workspaces: ["workspaces"] as const,
  workspace: (ws: string) => ["workspace", ws] as const,
  sources: (ws: string) => ["workspace", ws, "sources"] as const,
  source: (ws: string, id: string) => ["workspace", ws, "sources", id] as const,
  evidence: (ws: string, handle: string, child: string | null) =>
    ["workspace", ws, "evidence", handle, child] as const,
  search: (ws: string, q: string, mode: SearchMode, k: number) =>
    ["workspace", ws, "search", q, mode, k] as const,
};

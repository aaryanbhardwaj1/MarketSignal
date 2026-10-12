import { evidenceApiPath, resultApiPath } from "../handles";
import { buildSearchQuery } from "../search";
import { API_BASE_URL } from "./config";
import { apiGet, apiRequest } from "./client";
import type {
  CancelRunResult,
  ChatMessage,
  CreateConversationInput,
  CreateConversationResult,
  Evidence,
  ResultEnvelope,
  SearchParams,
  SearchResponse,
  SourceDetail,
  SourceSummary,
  StartRunInput,
  StartRunResult,
  Workspace,
} from "./types";

const ws = (code: string) => `/api/workspaces/${encodeURIComponent(code)}`;

export const listWorkspaces = (signal?: AbortSignal) =>
  apiGet<Workspace[]>("/api/workspaces", { signal });

export const listSources = (code: string, signal?: AbortSignal) =>
  apiGet<SourceSummary[]>(`${ws(code)}/sources`, { signal });

export const getSource = (code: string, sourceId: string, signal?: AbortSignal) =>
  apiGet<SourceDetail>(`${ws(code)}/sources/${encodeURIComponent(sourceId)}`, { signal });

export const getEvidence = (
  code: string,
  handle: string,
  childId?: string | null,
  signal?: AbortSignal,
) => apiGet<Evidence>(evidenceApiPath(code, handle), { query: { child_id: childId }, signal });

export const getResult = (code: string, resultId: string, signal?: AbortSignal) =>
  apiGet<ResultEnvelope>(resultApiPath(code, resultId), { signal });

export const searchWorkspace = (code: string, params: SearchParams, signal?: AbortSignal) =>
  apiGet<SearchResponse>(`${ws(code)}/search?${buildSearchQuery(params)}`, { signal });

export async function createConversation(
  code: string,
  input: CreateConversationInput = {},
): Promise<CreateConversationResult> {
  const res = await apiRequest<CreateConversationResult>(`${ws(code)}/conversations`, {
    method: "POST",
    json: input,
  });
  return res.data;
}

export const listMessages = (code: string, conversationId: string, signal?: AbortSignal) =>
  apiGet<ChatMessage[]>(
    `${ws(code)}/conversations/${encodeURIComponent(conversationId)}/messages`,
    { signal },
  );

export async function startRun(
  code: string,
  conversationId: string,
  input: StartRunInput,
): Promise<StartRunResult> {
  const res = await apiRequest<StartRunResult>(
    `${ws(code)}/conversations/${encodeURIComponent(conversationId)}/runs`,
    { method: "POST", json: input },
  );
  return res.data;
}

export async function cancelRun(code: string, runId: string): Promise<CancelRunResult> {
  const res = await apiRequest<CancelRunResult>(
    `${ws(code)}/runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );
  return res.data;
}

/**
 * Absolute EventSource URL for a run's `stream_url`. Only same-API paths are accepted
 * (`/api/...`, no scheme, no protocol-relative `//host`), so a malformed response can never
 * point the stream at another origin. Returns null when the path is rejected.
 */
export function runStreamUrl(streamPath: string, base: string = API_BASE_URL): string | null {
  if (typeof streamPath !== "string" || !streamPath.startsWith("/api/")) return null;
  if (/[\\\s]/.test(streamPath)) return null;
  return `${base}${streamPath}`;
}

import { evidenceApiPath } from "../handles";
import { apiGet, apiRequest } from "./client";
import type {
  CreateWorkspaceInput,
  DeleteSourceResult,
  Evidence,
  SearchMode,
  SearchResponse,
  SourceDetail,
  SourceSummary,
  UploadSourceInput,
  UploadSourceResult,
  Workspace,
  WorkspaceDetail,
} from "./types";

const ws = (code: string) => `/api/workspaces/${encodeURIComponent(code)}`;

export const listWorkspaces = (signal?: AbortSignal) =>
  apiGet<Workspace[]>("/api/workspaces", { signal });

export const getWorkspace = (code: string, signal?: AbortSignal) =>
  apiGet<WorkspaceDetail>(ws(code), { signal });

export async function createWorkspace(input: CreateWorkspaceInput): Promise<Workspace> {
  const res = await apiRequest<Workspace>("/api/workspaces", { method: "POST", json: input });
  return res.data;
}

export const listSources = (code: string, signal?: AbortSignal) =>
  apiGet<SourceSummary[]>(`${ws(code)}/sources`, { signal });

export const getSource = (code: string, sourceId: string, signal?: AbortSignal) =>
  apiGet<SourceDetail>(`${ws(code)}/sources/${encodeURIComponent(sourceId)}`, { signal });

export async function uploadSource(code: string, input: UploadSourceInput): Promise<UploadSourceResult> {
  const form = new FormData();
  form.set("file", input.file);
  form.set("source_class", input.source_class);
  form.set("confidentiality", input.confidentiality);
  if (input.title) form.set("title", input.title);
  if (input.source_code) form.set("source_code", input.source_code);
  const res = await apiRequest<UploadSourceResult>(`${ws(code)}/sources`, { method: "POST", form });
  return res.data;
}

export async function deleteSource(code: string, sourceId: string): Promise<DeleteSourceResult> {
  const res = await apiRequest<DeleteSourceResult>(
    `${ws(code)}/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  );
  return res.data;
}

export async function retrySource(code: string, sourceId: string): Promise<unknown> {
  const res = await apiRequest<unknown>(
    `${ws(code)}/sources/${encodeURIComponent(sourceId)}/retry`,
    { method: "POST" },
  );
  return res.data;
}

export const getEvidence = (
  code: string,
  handle: string,
  childId?: string | null,
  signal?: AbortSignal,
) => apiGet<Evidence>(evidenceApiPath(code, handle), { query: { child_id: childId }, signal });

export const devSearch = (
  code: string,
  params: { q: string; mode: SearchMode; k?: number },
  signal?: AbortSignal,
) =>
  apiGet<SearchResponse>(`${ws(code)}/dev/search`, {
    query: { q: params.q, mode: params.mode, k: params.k ?? 10 },
    signal,
  });

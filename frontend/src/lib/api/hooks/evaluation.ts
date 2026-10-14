"use client";

/**
 * Evaluation catalog hooks (developer tools, E11). The catalog is precomputed from committed
 * evaluation artifacts; these endpoints exist only in development builds, so a 404 means
 * "catalog not served here" rather than an error to retry.
 */

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { apiGet } from "../client";
import type { EvalCatalog, EvalItemsPage, EvalRunId, RagasItemsPage, RagasRunId } from "../contracts";

export const EVAL_ITEMS_MAX_LIMIT = 50;

export interface EvalItemsParams {
  offset?: number;
  limit?: number;
  bucket?: string | null;
}

export const evaluationKeys = {
  all: ["dev-eval"] as const,
  catalog: ["dev-eval", "catalog"] as const,
  items: (runId: EvalRunId, params: Required<EvalItemsParams>) =>
    ["dev-eval", "runs", runId, "items", params] as const,
};

function normalise(params: EvalItemsParams = {}): Required<EvalItemsParams> {
  const limit = Math.min(Math.max(Math.trunc(params.limit ?? 20), 1), EVAL_ITEMS_MAX_LIMIT);
  const offset = Math.max(Math.trunc(params.offset ?? 0), 0);
  return { offset, limit, bucket: params.bucket || null };
}

export const getEvalCatalog = (signal?: AbortSignal): Promise<EvalCatalog> =>
  apiGet<EvalCatalog>("/api/dev/eval/catalog", { signal });

export const getEvalItems = (
  runId: EvalRunId,
  params: EvalItemsParams = {},
  signal?: AbortSignal,
): Promise<EvalItemsPage> => {
  const { offset, limit, bucket } = normalise(params);
  return apiGet<EvalItemsPage>(`/api/dev/eval/runs/${encodeURIComponent(runId)}/items`, {
    query: { offset, limit, bucket },
    signal,
  });
};

/** The whole evaluation catalog. Static per build, so it is cached for the session. */
export function useEvalCatalog(): UseQueryResult<EvalCatalog> {
  return useQuery({
    queryKey: evaluationKeys.catalog,
    queryFn: ({ signal }) => getEvalCatalog(signal),
    staleTime: Infinity,
    retry: false,
  });
}

/** One page of evaluation items for a run; keeps the previous page visible while paging. */
export function useEvalItems(
  runId: EvalRunId | null,
  params: EvalItemsParams = {},
): UseQueryResult<EvalItemsPage> {
  const normalised = normalise(params);
  return useQuery({
    queryKey: runId ? evaluationKeys.items(runId, normalised) : [...evaluationKeys.all, "runs", "none"],
    queryFn: ({ signal }) => getEvalItems(runId as EvalRunId, normalised, signal),
    enabled: runId !== null,
    staleTime: Infinity,
    retry: false,
    placeholderData: keepPreviousData,
  });
}

// ── E13 RAGAS items (same paged endpoint; `bucket` is the configuration name) ──────────────

export interface RagasItemsParams {
  offset?: number;
  limit?: number;
  configuration?: string | null;
}

export const ragasKeys = {
  items: (runId: RagasRunId, params: Required<EvalItemsParams>) =>
    ["dev-eval", "ragas", runId, "items", params] as const,
};

const ragasParams = ({ configuration, ...rest }: RagasItemsParams = {}): Required<EvalItemsParams> =>
  normalise({ ...rest, bucket: configuration ?? null });

export const getRagasItems = (
  runId: RagasRunId,
  params: RagasItemsParams = {},
  signal?: AbortSignal,
): Promise<RagasItemsPage> => {
  const { offset, limit, bucket } = ragasParams(params);
  return apiGet<RagasItemsPage>(`/api/dev/eval/runs/${encodeURIComponent(runId)}/items`, {
    query: { offset, limit, bucket },
    signal,
  });
};

/** One page of per-item RAGAS scores, optionally for one configuration (standard/research). */
export function useRagasItems(
  runId: RagasRunId | null,
  params: RagasItemsParams = {},
): UseQueryResult<RagasItemsPage> {
  const normalised = ragasParams(params);
  return useQuery({
    queryKey: runId ? ragasKeys.items(runId, normalised) : [...evaluationKeys.all, "ragas", "none"],
    queryFn: ({ signal }) =>
      getRagasItems(
        runId as RagasRunId,
        { offset: normalised.offset, limit: normalised.limit, configuration: normalised.bucket },
        signal,
      ),
    enabled: runId !== null,
    staleTime: Infinity,
    retry: false,
    placeholderData: keepPreviousData,
  });
}

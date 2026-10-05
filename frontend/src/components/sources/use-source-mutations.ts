"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteSource, retrySource } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";

export function useSourceMutations(ws: string) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.sources(ws) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.workspace(ws), exact: true }),
    ]);

  const retry = useMutation({
    mutationFn: (sourceId: string) => retrySource(ws, sourceId),
    onSettled: invalidate,
  });

  const remove = useMutation({
    mutationFn: (sourceId: string) => deleteSource(ws, sourceId),
    onSettled: invalidate,
  });

  return { retry, remove, invalidate };
}

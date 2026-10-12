"use client";

import { ResultCard } from "./result-card";

/** Drawer body for `GET /results/{id}`: a computed result, never shaped like an evidence passage. */
export function ResultDetail({ ws, resultId }: { ws: string; resultId: string }) {
  return <ResultCard ws={ws} resultId={resultId} />;
}

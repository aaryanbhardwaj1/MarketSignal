/**
 * Typed href builders for every in-app route. Workspace codes and ids are URL-encoded here, so
 * callers never hand-build `/w/${ws}/...` strings.
 */

const enc = encodeURIComponent;

/** `/w/{ws}`: the root of one workspace. */
export function workspaceHref(ws: string): string {
  return `/w/${enc(ws)}`;
}

export function overviewHref(ws: string): string {
  return `${workspaceHref(ws)}/overview`;
}

/** Ask MarketSignal; with a conversation id, that saved conversation (`/ask/{conversationId}`). */
export function askHref(ws: string, conversationId?: string | null): string {
  const base = `${workspaceHref(ws)}/ask`;
  return conversationId ? `${base}/${enc(conversationId)}` : base;
}

export function opportunitiesHref(ws: string): string {
  return `${workspaceHref(ws)}/opportunities`;
}

export function opportunityHref(ws: string, opportunityId: string): string {
  return `${opportunitiesHref(ws)}/${enc(opportunityId)}`;
}

/** Analytics; `section` jumps to an in-page anchor such as `datasets` or `saved-results`. */
export function analyticsHref(ws: string, section?: "datasets" | "saved-results"): string {
  const base = `${workspaceHref(ws)}/analytics`;
  return section ? `${base}#${section}` : base;
}

export function analysisHref(ws: string, analysisId: string): string {
  return `${analyticsHref(ws)}/${enc(analysisId)}`;
}

/** Evidence Library; optional search params (e.g. `{ q }`, `{ ev }`) are appended as a query string. */
export function evidenceLibraryHref(ws: string, params?: Readonly<Record<string, string>> | URLSearchParams): string {
  const base = `${workspaceHref(ws)}/evidence`;
  const qs = params ? new URLSearchParams(params).toString() : "";
  return qs ? `${base}?${qs}` : base;
}

export function sourceHref(ws: string, sourceId: string): string {
  return `${evidenceLibraryHref(ws)}/sources/${enc(sourceId)}`;
}

export function telemetryHref(ws: string): string {
  return `${workspaceHref(ws)}/dev/telemetry`;
}

export function telemetryRunHref(ws: string, runId: string): string {
  return `${telemetryHref(ws)}/runs/${enc(runId)}`;
}

/** RAG Evaluation base path; tab and run links are built by `evalHref` / `evalRunHref` in `lib/eval-view`. */
export function evaluationHref(ws: string): string {
  return `${workspaceHref(ws)}/dev/evaluation`;
}

/** Ask MarketSignal links. Ids are URL-encoded; the workspace code is too. */
const base = (ws: string) => `/w/${encodeURIComponent(ws)}`;

export const askHref = (ws: string, conversationId?: string | null): string =>
  conversationId ? `${base(ws)}/ask/${encodeURIComponent(conversationId)}` : `${base(ws)}/ask`;

export const telemetryRunHref = (ws: string, runId: string): string =>
  `${base(ws)}/dev/telemetry/runs/${encodeURIComponent(runId)}`;

export const evidenceLibraryHref = (ws: string): string => `${base(ws)}/evidence`;

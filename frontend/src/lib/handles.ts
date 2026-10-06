/**
 * Evidence handle helpers. Canonical handles look like
 * `NORTHSTAR/SURVEY-2026@v1:R185` and contain '/', '@' and ':', so they must always be
 * percent-encoded as a single path segment or query value.
 */

const HANDLE_PATTERN =
  /^([A-Z][A-Z0-9]{1,15})\/([A-Z0-9]{1,12}(?:-[A-Z0-9]{1,12}){0,5})@v(\d+):(\S+)$/;

export interface ParsedHandle {
  workspace: string;
  sourceCode: string;
  version: number;
  locator: string;
}

/** Best-effort client-side parse; the API remains the authority on validity. */
export function parseHandle(handle: string): ParsedHandle | null {
  const match = HANDLE_PATTERN.exec(handle.trim());
  if (!match) return null;
  return {
    workspace: match[1],
    sourceCode: match[2],
    version: Number(match[3]),
    locator: match[4],
  };
}

/** Same source + locator at a different version, or null when the handle cannot be parsed. */
export function handleAtVersion(handle: string, version: number): string | null {
  const parsed = parseHandle(handle);
  if (!parsed || !Number.isInteger(version) || version < 1) return null;
  return `${parsed.workspace}/${parsed.sourceCode}@v${version}:${parsed.locator}`;
}

/** API path for evidence resolution; the handle is encoded as one opaque segment. */
export function evidenceApiPath(workspace: string, handle: string): string {
  return `/api/workspaces/${encodeURIComponent(workspace)}/evidence/${encodeURIComponent(handle)}`;
}

/** In-app link to the evidence viewer, e.g. `/w/NORTHSTAR/evidence?h=...&child=...`. */
export function evidenceViewerHref(workspace: string, handle: string, childId?: string | null): string {
  const params = new URLSearchParams({ h: handle });
  if (childId) params.set("child", childId);
  return `/w/${encodeURIComponent(workspace)}/evidence?${params.toString()}`;
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value);
}

/** API path for a computed analytics result. */
export function resultApiPath(workspace: string, resultId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspace)}/results/${encodeURIComponent(resultId)}`;
}

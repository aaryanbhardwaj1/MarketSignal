/**
 * Redirect targets for the entry routes and the legacy routes (plan §3). Pure functions so the
 * server `redirect()` stubs stay one line and the mapping is unit-tested.
 */
import { DEFAULT_WORKSPACE, isTestWorkspace, workspaceBase } from "./nav";

type ParamValue = string | string[] | undefined;

function first(value: ParamValue): string | null {
  const v = Array.isArray(value) ? value[0] : value;
  const trimmed = v?.trim();
  return trimmed ? trimmed : null;
}

/** `/` lands on NORTHSTAR when it is visible, else the first visible workspace, else NORTHSTAR. */
export function rootRedirectTarget(workspaces: ReadonlyArray<{ code: string }> | null): string {
  const visible = (workspaces ?? []).filter((w) => !isTestWorkspace(w.code));
  const chosen = visible.find((w) => w.code === DEFAULT_WORKSPACE) ?? visible[0];
  return `${workspaceBase(chosen?.code ?? DEFAULT_WORKSPACE)}/overview`;
}

export function workspaceRootTarget(ws: string): string {
  return `${workspaceBase(ws)}/overview`;
}

/** `/chat?c=X` → `/ask/X`; bare `/chat` → `/ask`. */
export function chatRedirectTarget(ws: string, c: ParamValue): string {
  const id = first(c);
  return id ? `${workspaceBase(ws)}/ask/${encodeURIComponent(id)}` : `${workspaceBase(ws)}/ask`;
}

export function sourcesRedirectTarget(ws: string): string {
  return `${workspaceBase(ws)}/evidence`;
}

export function sourceDetailRedirectTarget(ws: string, sourceId: string): string {
  return `${workspaceBase(ws)}/evidence/sources/${encodeURIComponent(sourceId)}`;
}

/** `/search?q=` → `/evidence?q=` (mode and score options are dropped: the library hides them). */
export function searchRedirectTarget(ws: string, q: ParamValue): string {
  const query = first(q);
  const base = `${workspaceBase(ws)}/evidence`;
  return query ? `${base}?${new URLSearchParams({ q: query }).toString()}` : base;
}

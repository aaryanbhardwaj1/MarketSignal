/**
 * Redirect targets for the entry routes and the legacy routes (plan §3). Pure functions so the
 * server `redirect()` stubs stay one line and the mapping is unit-tested.
 */
import { askHref, evidenceLibraryHref, insightsHref, sourceHref } from "@/lib/routes";
import { DEFAULT_WORKSPACE, isTestWorkspace } from "./nav";

type ParamValue = string | string[] | undefined;

function first(value: ParamValue): string | null {
  const v = Array.isArray(value) ? value[0] : value;
  const trimmed = v?.trim();
  return trimmed ? trimmed : null;
}

/** `/` opens Chat in NORTHSTAR when it is visible, else the first visible workspace, else NORTHSTAR. */
export function rootRedirectTarget(workspaces: ReadonlyArray<{ code: string }> | null): string {
  const visible = (workspaces ?? []).filter((w) => !isTestWorkspace(w.code));
  const chosen = visible.find((w) => w.code === DEFAULT_WORKSPACE) ?? visible[0];
  return askHref(chosen?.code ?? DEFAULT_WORKSPACE);
}

/** `/w/{ws}` opens Chat. */
export function workspaceRootTarget(ws: string): string {
  return askHref(ws);
}

/** The former Overview page is now Insights. */
export function overviewRedirectTarget(ws: string): string {
  return insightsHref(ws);
}

/** `/chat?c=X` → `/ask/X`; bare `/chat` → `/ask`. */
export function chatRedirectTarget(ws: string, c: ParamValue): string {
  const id = first(c);
  return askHref(ws, id);
}

export function sourcesRedirectTarget(ws: string): string {
  return evidenceLibraryHref(ws);
}

export function sourceDetailRedirectTarget(ws: string, sourceId: string): string {
  return sourceHref(ws, sourceId);
}

/** `/search?q=` → `/evidence?q=` (mode and score options are dropped: the library hides them). */
export function searchRedirectTarget(ws: string, q: ParamValue): string {
  const query = first(q);
  return query ? evidenceLibraryHref(ws, { q: query }) : evidenceLibraryHref(ws);
}

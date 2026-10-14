/**
 * Navigation model. The top bar carries the four business sections (`PRIMARY_NAV`) and, to the
 * right, the two developer tools (`DEV_TOOLS`). The Evidence library is a section without a nav
 * entry (reached from the workspace popover and provenance links). Labels are product copy;
 * hrefs are built per workspace code, which only ever appears in URLs.
 */

import { workspaceHref } from "@/lib/routes";

export type NavGroupName = "Primary" | "Developer tools";
export type NavId = "ask" | "insights" | "opportunities" | "analytics" | "evidence" | "telemetry" | "evaluation";

export interface NavItem {
  id: NavId;
  label: string;
  /** Path segment(s) under `/w/{ws}/`. */
  segment: string;
  /** Older segments that still resolve to this section (they redirect). */
  aliases?: readonly string[];
  href: (ws: string) => string;
}

const item = (id: NavId, label: string, segment: string, aliases?: readonly string[]): NavItem => ({
  id,
  label,
  segment,
  aliases,
  href: (ws) => `${workspaceBase(ws)}/${segment}`,
});

/** Chat · Insights · Growth Opportunities · Analytics, in this order. */
export const PRIMARY_NAV: readonly NavItem[] = [
  item("ask", "Chat", "ask", ["chat"]),
  item("insights", "Insights", "insights", ["overview"]),
  item("opportunities", "Growth Opportunities", "opportunities"),
  item("analytics", "Analytics", "analytics"),
];

/** Developer tooling, shown as icon buttons on the right of the top bar. */
export const DEV_TOOLS: readonly NavItem[] = [
  item("telemetry", "Telemetry", "dev/telemetry"),
  item("evaluation", "RAG Evaluation", "dev/evaluation"),
];

/** Sections without a nav entry that still count as "where you are" (e.g. for switching workspace). */
export const EVIDENCE_SECTION: NavItem = item("evidence", "Evidence library", "evidence", ["sources", "search"]);

export const NAV_ITEMS: readonly NavItem[] = [...PRIMARY_NAV, EVIDENCE_SECTION, ...DEV_TOOLS];

export const DEFAULT_WORKSPACE = "NORTHSTAR";

/** Test-harness workspaces are named with codes like `T0123456789`; never listed in the UI. */
export const TEST_WORKSPACE_CODE = /^T[0-9A-F]{10}$/;

export function workspaceBase(ws: string): string {
  return workspaceHref(ws);
}

/** Path segments after `/w/{ws}/`, or null when the path is outside this workspace. */
function workspaceRest(pathname: string, ws: string): string[] | null {
  const parts = pathname.split("?")[0].split("/").filter(Boolean);
  if (parts[0] !== "w" || parts.length < 2) return null;
  let code: string;
  try {
    code = decodeURIComponent(parts[1]);
  } catch {
    code = parts[1];
  }
  return code === ws ? parts.slice(2) : null;
}

const underSegment = (path: string, segment: string) => path === segment || path.startsWith(`${segment}/`);

/** The section a pathname belongs to (longest matching segment wins, aliases included), or null. */
export function activeNavId(pathname: string, ws: string): NavId | null {
  const rest = workspaceRest(pathname, ws);
  if (!rest || rest.length === 0) return null;
  const path = rest.join("/");
  let best: { id: NavId; length: number } | null = null;
  for (const entry of NAV_ITEMS) {
    for (const segment of [entry.segment, ...(entry.aliases ?? [])]) {
      if (underSegment(path, segment) && (!best || segment.length > best.length)) {
        best = { id: entry.id, length: segment.length };
      }
    }
  }
  return best?.id ?? null;
}

/**
 * Where switching to workspace `to` should land: the same section (not the same record, since
 * ids are workspace-scoped), or Chat when the current page is not a known section.
 */
export function switchWorkspaceHref(pathname: string, from: string, to: string): string {
  const id = activeNavId(pathname, from);
  const target = NAV_ITEMS.find((n) => n.id === id) ?? PRIMARY_NAV[0];
  return target.href(to);
}

export function isTestWorkspace(code: string): boolean {
  return TEST_WORKSPACE_CODE.test(code);
}

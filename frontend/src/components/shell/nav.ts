/**
 * Primary navigation (plan §3). Labels are product copy; hrefs are built per workspace code.
 * The workspace code only appears in URLs, never as visible text.
 */

export type NavGroupName = "Workspace" | "Developer tools";
export type NavId =
  | "overview"
  | "ask"
  | "opportunities"
  | "analytics"
  | "evidence"
  | "telemetry"
  | "evaluation";

export interface NavItem {
  id: NavId;
  label: string;
  /** Path segment(s) under `/w/{ws}/`. */
  segment: string;
  href: (ws: string) => string;
}

export interface NavGroup {
  group: NavGroupName;
  items: NavItem[];
}

const item = (id: NavId, label: string, segment: string): NavItem => ({
  id,
  label,
  segment,
  href: (ws) => `${workspaceBase(ws)}/${segment}`,
});

export const NAV: readonly NavGroup[] = [
  {
    group: "Workspace",
    items: [
      item("overview", "Overview", "overview"),
      item("ask", "Ask MarketSignal", "ask"),
      item("opportunities", "Growth Opportunities", "opportunities"),
      item("analytics", "Analytics", "analytics"),
      item("evidence", "Evidence Library", "evidence"),
    ],
  },
  {
    group: "Developer tools",
    items: [
      item("telemetry", "Telemetry", "dev/telemetry"),
      item("evaluation", "RAG Evaluation", "dev/evaluation"),
    ],
  },
];

export const NAV_ITEMS: readonly NavItem[] = NAV.flatMap((g) => g.items);

export const DEFAULT_WORKSPACE = "NORTHSTAR";

/** Test-harness workspaces are named with codes like `T0123456789`; never listed in the UI. */
export const TEST_WORKSPACE_CODE = /^T[0-9A-F]{10}$/;

export function workspaceBase(ws: string): string {
  return `/w/${encodeURIComponent(ws)}`;
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

/** The nav item a pathname belongs to (longest matching segment wins), or null. */
export function activeNavId(pathname: string, ws: string): NavId | null {
  const rest = workspaceRest(pathname, ws);
  if (!rest || rest.length === 0) return null;
  const path = rest.join("/");
  let best: NavItem | null = null;
  for (const entry of NAV_ITEMS) {
    const matches = path === entry.segment || path.startsWith(`${entry.segment}/`);
    if (matches && (!best || entry.segment.length > best.segment.length)) best = entry;
  }
  return best?.id ?? null;
}

/**
 * Where switching to workspace `to` should land: the same section (not the same record, since
 * ids are workspace-scoped), or the overview when the current page is not a nav section.
 */
export function switchWorkspaceHref(pathname: string, from: string, to: string): string {
  const id = activeNavId(pathname, from);
  const target = NAV_ITEMS.find((n) => n.id === id);
  return target ? target.href(to) : `${workspaceBase(to)}/overview`;
}

export function isTestWorkspace(code: string): boolean {
  return TEST_WORKSPACE_CODE.test(code);
}

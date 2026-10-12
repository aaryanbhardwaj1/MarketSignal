/**
 * URL state of the evidence drawer: `?ev=<handle>&child=<id>` for an evidence passage and
 * `?res=<id>` for a computed result. The legacy `?h=` (old evidence viewer links) is read as `ev`.
 */

export type DrawerTarget =
  | { kind: "evidence"; handle: string; childId: string | null }
  | { kind: "result"; resultId: string };

export const DRAWER_PARAMS = ["ev", "h", "child", "res"] as const;

interface ReadableParams {
  get(name: string): string | null;
}

const clean = (value: string | null): string | null => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
};

export function parseDrawerParams(params: ReadableParams): DrawerTarget | null {
  const handle = clean(params.get("ev")) ?? clean(params.get("h"));
  if (handle) return { kind: "evidence", handle, childId: clean(params.get("child")) };
  const resultId = clean(params.get("res"));
  return resultId ? { kind: "result", resultId } : null;
}

/** `pathname?<other params>&<drawer params>`; other params (filters, tabs) are preserved. */
export function drawerHref(pathname: string, current: string | URLSearchParams, target: DrawerTarget | null): string {
  const next = new URLSearchParams(current);
  for (const name of DRAWER_PARAMS) next.delete(name);
  if (target?.kind === "evidence") {
    next.set("ev", target.handle);
    if (target.childId) next.set("child", target.childId);
  } else if (target?.kind === "result") {
    next.set("res", target.resultId);
  }
  const qs = next.toString();
  return qs ? `${pathname}?${qs}` : pathname;
}

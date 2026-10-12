import { describe, expect, it } from "vitest";
import { drawerHref, parseDrawerParams } from "./drawer-params";

const H = "NORTHSTAR/BRAND-STRATEGY@v1:P4.B2";

describe("parseDrawerParams", () => {
  it("reads ev, the legacy h, child and res", () => {
    expect(parseDrawerParams(new URLSearchParams({ ev: H, child: "c1" }))).toEqual({ kind: "evidence", handle: H, childId: "c1" });
    expect(parseDrawerParams(new URLSearchParams({ h: H }))).toEqual({ kind: "evidence", handle: H, childId: null });
    expect(parseDrawerParams(new URLSearchParams({ res: "r1" }))).toEqual({ kind: "result", resultId: "r1" });
    expect(parseDrawerParams(new URLSearchParams({ q: "x" }))).toBeNull();
    expect(parseDrawerParams(new URLSearchParams({ ev: "  " }))).toBeNull();
  });
});

describe("drawerHref", () => {
  it("sets drawer params and preserves the others", () => {
    const href = drawerHref("/w/NORTHSTAR/evidence", "?q=gen+z&h=old&child=x", { kind: "evidence", handle: H, childId: null });
    const url = new URL(href, "http://x");
    expect(url.pathname).toBe("/w/NORTHSTAR/evidence");
    expect(url.searchParams.get("q")).toBe("gen z");
    expect(url.searchParams.get("ev")).toBe(H);
    expect(url.searchParams.has("h")).toBe(false);
    expect(url.searchParams.has("child")).toBe(false);
  });

  it("clears drawer params on close", () => {
    expect(drawerHref("/w/N/ask", "?res=r1&tab=a", null)).toBe("/w/N/ask?tab=a");
    expect(drawerHref("/w/N/ask", `?ev=${encodeURIComponent(H)}`, null)).toBe("/w/N/ask");
  });
});

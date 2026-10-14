import { describe, expect, it } from "vitest";
import { estimateTextWidth, truncateToWidth, visibleLabels, wrapLabel } from "./label-layout";

describe("estimateTextWidth", () => {
  it("grows with length and treats wide glyphs as wider", () => {
    expect(estimateTextWidth("")).toBe(0);
    expect(estimateTextWidth("abcd")).toBeGreaterThan(estimateTextWidth("ab"));
    expect(estimateTextWidth("WWW")).toBeGreaterThan(estimateTextWidth("iii"));
    expect(estimateTextWidth("abc", 22)).toBeCloseTo(estimateTextWidth("abc", 11) * 2);
  });
});

describe("truncateToWidth", () => {
  it("keeps text that fits and ellipsises text that does not", () => {
    expect(truncateToWidth("Campus", 200)).toBe("Campus");
    const cut = truncateToWidth("Established Active Customers", 60);
    expect(cut.endsWith("…")).toBe(true);
    expect(estimateTextWidth(cut)).toBeLessThanOrEqual(60);
  });
  it("falls back to an ellipsis when nothing fits", () => {
    expect(truncateToWidth("Campus", 2)).toBe("…");
  });
});

describe("wrapLabel", () => {
  it("leaves short labels on one line", () => {
    expect(wrapLabel("Campus", 120)).toEqual({ lines: ["Campus"], truncated: false });
  });
  it("wraps at word boundaries onto a second line", () => {
    const out = wrapLabel("Campus Competitors", 80);
    expect(out).toEqual({ lines: ["Campus", "Competitors"], truncated: false });
  });
  it("never exceeds maxLines and truncates the overflow with an ellipsis", () => {
    const out = wrapLabel("Established active customers in urban areas", 80);
    expect(out.lines).toHaveLength(2);
    expect(out.lines[1].endsWith("…")).toBe(true);
    expect(out.truncated).toBe(true);
    out.lines.forEach((line) => expect(estimateTextWidth(line)).toBeLessThanOrEqual(80));
  });
  it("truncates a single word longer than the line", () => {
    const out = wrapLabel("Supercalifragilistic", 50, { maxLines: 2 });
    expect(out.lines).toHaveLength(1);
    expect(out.lines[0].endsWith("…")).toBe(true);
    expect(out.truncated).toBe(true);
  });
  it("supports a single line and empty input", () => {
    expect(wrapLabel("Campus Competitors", 80, { maxLines: 1 }).lines).toHaveLength(1);
    expect(wrapLabel("   ", 80)).toEqual({ lines: [], truncated: false });
  });
});

describe("visibleLabels", () => {
  it("shows labels with room and hides ones that would overlap an earlier label", () => {
    const labels = [
      { x: 10, y: 50, text: "1,200" },
      { x: 18, y: 50, text: "1,350" },
      { x: 100, y: 50, text: "980" },
    ];
    expect(visibleLabels(labels)).toEqual([true, false, true]);
  });
  it("keeps horizontally overlapping labels when their baselines are a line apart", () => {
    expect(visibleLabels([{ x: 10, y: 20, text: "40%" }, { x: 14, y: 80, text: "38%" }])).toEqual([true, true]);
  });
  it("never draws empty labels", () => {
    expect(visibleLabels([{ x: 10, y: 10, text: "" }, { x: 10, y: 10, text: "5" }])).toEqual([false, true]);
  });
  it("respects the text anchor", () => {
    const labels = [
      { x: 0, y: 10, text: "Jan 2026", anchor: "start" as const },
      { x: 120, y: 10, text: "Dec 2026", anchor: "end" as const },
    ];
    expect(visibleLabels(labels)).toEqual([true, true]);
  });
});

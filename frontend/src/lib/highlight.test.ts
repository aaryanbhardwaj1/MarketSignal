import { describe, expect, it } from "vitest";
import { resolveActiveSpan, segmentHighlight } from "./highlight";

const TEXT = "record_id: CP-2026; month: 2026-02";

describe("segmentHighlight", () => {
  it("splits text at the given offsets", () => {
    expect(segmentHighlight(TEXT, 11, 18)).toEqual({
      before: "record_id: ",
      mark: "CP-2026",
      after: "; month: 2026-02",
      valid: true,
    });
  });

  it("supports a span covering the whole text", () => {
    expect(segmentHighlight("abc", 0, 3)).toEqual({ before: "", mark: "abc", after: "", valid: true });
  });

  it("clamps out-of-range offsets", () => {
    expect(segmentHighlight("abcdef", -5, 3)).toEqual({
      before: "",
      mark: "abc",
      after: "def",
      valid: true,
    });
    expect(segmentHighlight("abcdef", 4, 999)).toEqual({
      before: "abcd",
      mark: "ef",
      after: "",
      valid: true,
    });
  });

  it("returns unmarked text for empty, inverted or fully out-of-range spans", () => {
    const unmarked = { before: "abcdef", mark: "", after: "", valid: false };
    expect(segmentHighlight("abcdef", 3, 3)).toEqual(unmarked);
    expect(segmentHighlight("abcdef", 5, 2)).toEqual(unmarked);
    expect(segmentHighlight("abcdef", 10, 20)).toEqual(unmarked);
    expect(segmentHighlight("abcdef", null, 3)).toEqual(unmarked);
    expect(segmentHighlight("abcdef", Number.NaN, 3)).toEqual(unmarked);
  });

  it("floors fractional offsets", () => {
    expect(segmentHighlight("abcdef", 1.7, 3.2).mark).toBe("bc");
  });

  it("counts code points like the Python backend", () => {
    const text = "a😀bc";
    // Python: len("a😀bc") == 4, text[2:4] == "bc"
    expect(segmentHighlight(text, 2, 4)).toEqual({ before: "a😀", mark: "bc", after: "", valid: true });
  });
});

describe("resolveActiveSpan", () => {
  const children = [
    { child_id: "a", char_start: 0, char_end: 10 },
    { child_id: "b", char_start: 8, char_end: 20 },
  ];

  it("prefers the server highlight", () => {
    const span = resolveActiveSpan(
      { children, highlight: { child_id: "b", char_start: 8, char_end: 20, text: "x" } },
      "b",
    );
    expect(span).toEqual({ childId: "b", charStart: 8, charEnd: 20, expectedText: "x" });
  });

  it("falls back to the selected child's offsets", () => {
    const span = resolveActiveSpan(
      { children, highlight: { child_id: "b", char_start: 8, char_end: 20, text: "x" } },
      "a",
    );
    expect(span).toEqual({ childId: "a", charStart: 0, charEnd: 10, expectedText: null });
  });

  it("returns null when nothing matches", () => {
    expect(resolveActiveSpan({ children, highlight: null }, null)).toBeNull();
    expect(resolveActiveSpan({ children, highlight: null }, "zzz")).toBeNull();
  });
});

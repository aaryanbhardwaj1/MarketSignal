import { describe, expect, it } from "vitest";
import { PREFILL_MAX_CHARS, prefillQuestion, withoutQuery } from "./ask-prefill";

describe("prefillQuestion", () => {
  it("trims the question and ignores empty values", () => {
    expect(prefillQuestion("  Why are returns rising?  ")).toBe("Why are returns rising?");
    expect(prefillQuestion("   ")).toBeNull();
    expect(prefillQuestion(null)).toBeNull();
    expect(prefillQuestion(undefined)).toBeNull();
  });

  it("caps the question at 2000 characters", () => {
    const long = "a".repeat(PREFILL_MAX_CHARS + 500);
    expect(prefillQuestion(long)).toHaveLength(PREFILL_MAX_CHARS);
    expect(PREFILL_MAX_CHARS).toBe(2000);
  });

  it("decodes as plain text, never markup", () => {
    const params = new URLSearchParams(`q=${encodeURIComponent("<b>Gen Z</b> & pricing?")}`);
    expect(prefillQuestion(params.get("q"))).toBe("<b>Gen Z</b> & pricing?");
  });
});

describe("withoutQuery", () => {
  it("removes q and keeps other params", () => {
    expect(withoutQuery(new URLSearchParams("q=hello&ev=abc"))).toBe("?ev=abc");
    expect(withoutQuery(new URLSearchParams("q=hello"))).toBe("");
  });
});

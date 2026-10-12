import { describe, expect, it } from "vitest";
import { ApiError } from "./api/errors";
import { isModelUnavailable, isProviderUnavailableError } from "./model-availability";

describe("isModelUnavailable", () => {
  it("is false with no signals", () => {
    expect(isModelUnavailable({})).toBe(false);
    expect(
      isModelUnavailable({ warnings: ["PACK_BUDGET_TRUNCATED"], terminationState: "completed", flags: ["RERANKER_UNAVAILABLE"] }),
    ).toBe(false);
  });

  it("detects the synthesis-unavailable warning (string or object)", () => {
    expect(isModelUnavailable({ warnings: ["LLM_SYNTHESIS_UNAVAILABLE"] })).toBe(true);
    expect(isModelUnavailable({ warnings: [{ code: "LLM_SYNTHESIS_UNAVAILABLE" }] })).toBe(true);
  });

  it("detects the generation_unavailable termination", () => {
    expect(isModelUnavailable({ terminationState: "generation_unavailable" })).toBe(true);
  });

  it("detects the planner fallback flag", () => {
    expect(isModelUnavailable({ flags: ["PLANNER_UNAVAILABLE_FALLBACK"] })).toBe(true);
  });

  it("detects the evidence-only sections reason", () => {
    expect(isModelUnavailable({ sectionsReason: "LLM_SYNTHESIS_UNAVAILABLE" })).toBe(true);
    expect(isModelUnavailable({ sectionsReason: "CITATION_VERIFICATION_FAILED" })).toBe(false);
  });

  it("detects HTTP 503 PROVIDER_UNAVAILABLE only", () => {
    const err = new ApiError(503, "PROVIDER_UNAVAILABLE", "provider text never shown");
    expect(isModelUnavailable({ httpError: err })).toBe(true);
    expect(isProviderUnavailableError(err)).toBe(true);
    expect(isProviderUnavailableError(new ApiError(503, "OTHER", "x"))).toBe(false);
    expect(isProviderUnavailableError(new ApiError(500, "PROVIDER_UNAVAILABLE", "x"))).toBe(false);
    expect(isProviderUnavailableError(new Error("PROVIDER_UNAVAILABLE"))).toBe(false);
  });
});

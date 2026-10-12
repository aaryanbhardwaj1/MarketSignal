import { describe, expect, it } from "vitest";
import catalogJson from "@/lib/api/__fixtures__/evaluation-catalog.json";
import type { EvalCatalog, EvalMetric } from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import {
  MINUS,
  checkLabel,
  glossaryTitle,
  parsePageParam,
  catalogFailure,
  changeVerdict,
  deltaVerdict,
  formatCi,
  formatCountOf,
  formatEvalValue,
  formatSigned,
  gitForPath,
  groupGroundedMetrics,
  isEvalRunId,
  joinBySuffix,
  parseAnswer,
  pageWindow,
  parseHandle,
  provenanceForRun,
  formatCheck,
  formatCheckDelta,
  signTone,
  weakestCategory,
} from "./eval-view";

const catalog = catalogJson as unknown as EvalCatalog;
const src = { kind: "json" as const, path: "x.json", pointer: "/a" };
const delta = (value: number, lo: number, hi: number): EvalMetric => ({
  id: "d",
  label: "Δ",
  value,
  unit: "ratio",
  ci_low: lo,
  ci_high: hi,
  source: src,
});

describe("formatting", () => {
  it("keeps three decimals for ratios and signs deltas with a true minus", () => {
    expect(formatEvalValue(1, "ratio")).toBe("1.000");
    expect(formatSigned(-0.1666, "ratio")).toBe(`${MINUS}0.167`);
    expect(formatSigned(0.3235, "ratio")).toBe("+0.324");
    expect(formatSigned(0, "ratio")).toBe("0.000");
    expect(formatEvalValue(null, "ratio")).toBe("-");
  });

  it("formats CIs, signed when asked, and k / n", () => {
    const m = delta(-0.1667, -0.3431, -0.0196);
    expect(formatCi(m, { signed: true })).toBe(`95% CI ${MINUS}0.343 to ${MINUS}0.020`);
    expect(formatCi({ ...m, ci_low: undefined })).toBeNull();
    expect(formatCountOf({ k: 31, n: 54 })).toBe("31 / 54");
    expect(formatCountOf({ n: 17 })).toBe("n = 17");
    expect(formatCountOf({})).toBeNull();
  });
});

describe("deltaVerdict", () => {
  it("labels a CI that crosses 0 as not distinguishable", () => {
    expect(deltaVerdict(delta(0.04, -0.026, 0.13)).label).toBe("Not distinguishable");
    expect(deltaVerdict(delta(0.04, -0.026, 0.13)).tone).toBe("neutral");
  });

  it("gives a negative delta the warn tone", () => {
    const v = deltaVerdict(delta(-0.167, -0.343, -0.02));
    expect(v).toEqual({ label: "Worse", tone: "warn", distinguishable: true });
    expect(signTone(-0.167)).toBe("warn");
  });

  it("reads resource deltas against the lower-is-better direction", () => {
    expect(deltaVerdict(delta(2.9, 2.7, 3.2), "lower", { resource: true })).toMatchObject({
      label: "Costs more",
      tone: "warn",
    });
    expect(deltaVerdict({ value: 1, ci_low: undefined, ci_high: undefined }).label).toBe("No interval recorded");
  });

  it("reads before/after rates by direction", () => {
    expect(changeVerdict(0.13, 0.058, "lower").label).toBe("Improved");
    expect(changeVerdict(0.3, 0.3, "lower").label).toBe("No change");
    expect(changeVerdict(0.9, 0.8, "higher").label).toBe("Worse");
  });
});

describe("answer parsing", () => {
  it("splits headings, bullets and citation markers without keeping markup", () => {
    const blocks = parseAnswer("### Answer\n\nIt was **9.5 hours** [[NS/SUPPORT@v1:P3.B3]] [inference].\n\n- One [[NS/A@v1:T1]]");
    expect(blocks[0]).toEqual({ kind: "heading", parts: [{ kind: "text", text: "Answer" }] });
    expect(blocks[1].parts).toEqual([
      { kind: "text", text: "It was 9.5 hours " },
      { kind: "cite", handle: "NS/SUPPORT@v1:P3.B3" },
      { kind: "text", text: " " },
      { kind: "inference" },
      { kind: "text", text: "." },
    ]);
    expect(blocks[2].kind).toBe("bullet");
  });

  it("labels handles by source code and locator", () => {
    expect(parseHandle("NORTHSTAR/SUPPORT-THEMES@v1:P3.B3")).toEqual({ source: "SUPPORT-THEMES", locator: "P3.B3" });
    expect(parseHandle("plain")).toEqual({ source: "plain", locator: "" });
  });
});

describe("catalog helpers", () => {
  it("resolves git from the run that owns an artifact or its folder", () => {
    const grounded = catalog.grounded.provenance;
    expect(gitForPath(catalog, grounded.path)).toBe(grounded.git);
    const folder = grounded.path.slice(0, grounded.path.lastIndexOf("/"));
    expect(gitForPath(catalog, `${folder}/failure-analysis.json`)).toBe(grounded.git);
    expect(gitForPath(catalog, "docs/nowhere.md")).toBeNull();
  });

  it("joins analytics metrics across splits by id suffix", () => {
    const rows = joinBySuffix(catalog.analytics);
    const routing = rows.find((r) => r.key === "task_type_accuracy");
    expect(routing?.bySplit.dev).toBeDefined();
    expect(routing?.bySplit.holdout).toBeDefined();
  });

  it("names the weakest category and never drops grounded metrics", () => {
    const weakest = weakestCategory(catalog.grounded.by_category, "gold_coverage_mean");
    const values = catalog.grounded.by_category
      .flatMap((c) => c.metrics)
      .filter((m) => m.id.endsWith(".gold_coverage_mean"))
      .map((m) => m.value as number);
    expect(weakest?.metric.value).toBe(Math.min(...values));
    const grouped = groupGroundedMetrics(catalog.grounded.metrics).flatMap((g) => g.metrics.map((m) => m.id));
    for (const m of catalog.grounded.metrics) {
      if (m.id === "p3.citation_resolvability" || m.id === "p3.cross_workspace_leaks") continue;
      expect(grouped).toContain(m.id);
    }
  });

  it("treats 404 and EVAL_CATALOG_UNAVAILABLE as unavailable", () => {
    expect(catalogFailure(new ApiError(404, "NOT_FOUND", "x"))).toBe("unavailable");
    expect(catalogFailure(new ApiError(503, "EVAL_CATALOG_UNAVAILABLE", "x"))).toBe("unavailable");
    expect(catalogFailure(new ApiError(500, "INTERNAL", "x"))).toBe("error");
    expect(isEvalRunId("p2-test-c3")).toBe(true);
    expect(isEvalRunId("../etc")).toBe(false);
  });
});

describe("run helpers", () => {
  it("maps every failure run to a provenance block", () => {
    for (const r of catalog.failure_runs) {
      expect(provenanceForRun(catalog, r.run_id)).not.toBeNull();
    }
  });
  it("formats stored checks without inventing values", () => {
    expect(formatCheck("has_final", true)).toBe("Yes");
    expect(formatCheck("gold_coverage", 0.6666)).toBe("0.667");
    expect(formatCheck("citations", 2)).toBe("2");
    expect(formatCheck("x", null)).toBe("-");
  });
  it("signs per-item differences with a true minus", () => {
    expect(formatCheckDelta("model_calls", 4)).toBe("+4");
    expect(formatCheckDelta("first_token_ms", -87.1)).toBe(`${MINUS}87 ms`);
    expect(formatCheckDelta("gold_coverage", 0)).toBe("0.000");
  });
  it("describes the paging window", () => {
    expect(pageWindow(20, 20, 76)).toBe("21–40 of 76");
    expect(pageWindow(0, 0, 0)).toBe("0 of 0");
  });
});

describe("checkLabel", () => {
  it("uses explicit labels for known keys", () => {
    expect(checkLabel("first_token_ms")).toBe("First token");
    expect(checkLabel("has_done")).toBe("Stream completed");
    expect(checkLabel("southpeak_marker_leak")).toBe("Cross-workspace leak");
  });

  it("humanizes unknown keys and drops unit suffixes", () => {
    expect(checkLabel("synthesis_ms")).toBe("Synthesis");
    expect(checkLabel("llm_retries")).toBe("Model retries");
  });
});

describe("glossaryTitle", () => {
  it("names the term and its meaning", () => {
    expect(glossaryTitle("mrr")).toMatch(/^MRR: Mean reciprocal rank/);
  });
});

describe("parsePageParam", () => {
  it("reads positive integers and falls back to page 1", () => {
    expect(parsePageParam("3")).toBe(3);
    expect(parsePageParam(null)).toBe(1);
    expect(parsePageParam("0")).toBe(1);
    expect(parsePageParam("2.5")).toBe(1);
    expect(parsePageParam("abc")).toBe(1);
  });
});

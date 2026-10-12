import { describe, expect, it } from "vitest";
import type { ConversationSummary, RunRecord, RunVerification } from "./api/contracts";
import research from "./api/__fixtures__/core-run-6f18725e.json";
import standard from "./api/__fixtures__/core-run-fbffdd6b.json";
import verification from "./api/__fixtures__/core-verification-6f18725e.json";
import featured from "./api/__fixtures__/core-conversations-featured.json";
import { runMode, terminationState, verificationDisposition } from "./labels";
import {
  conversationOutcome,
  describeModeDecision,
  isAnsweredConversation,
  toSavedRunView,
  verificationLabel,
} from "./saved-run";

const mode = (code: string) => runMode(code).label;

const researchRun = research as unknown as RunRecord;
const standardRun = standard as unknown as RunRecord;
const researchVerification = verification as unknown as RunVerification;
const TITLES = { "SURVEY-2026": "Northstar Customer Survey 2026" };
const RAW_CODE = /[A-Z]{3,}_[A-Z_]+|SURVEY-2026|NORTHSTAR\/|[0-9a-f]{8}-[0-9a-f]{4}/;

describe("toSavedRunView (research run 6f18725e)", () => {
  const view = toSavedRunView(researchRun, researchVerification, { sourceTitles: TITLES });

  it("explains the Auto decision in plain words", () => {
    expect(view.mode).toBe(mode("research"));
    expect(view.modeCode).toBe("research");
    expect(view.modeReason).toBe(`${mode("auto")} mode chose ${mode("research")}: the question needed computed figures.`);
  });

  it("reports duration and the repaired verification", () => {
    expect(view.durationMs).toBe(17761.4);
    const repaired = verificationDisposition("repaired");
    const n = researchVerification.attempts[researchVerification.attempts.length - 1].repairs_n;
    expect(view.verification?.label).toBe(repaired.label);
    expect(view.verification?.tone).toBe(repaired.tone);
    expect(view.verification?.summary).toMatch(n > 0 ? new RegExp(`^Citations checked; ${n} correction`) : /^Citations checked/);
  });

  it("labels each saved research step in plain language", () => {
    expect(view.steps.map((s) => s.label)).toEqual([
      "Reviewed a dataset",
      "Searched the evidence library",
      "Computed a figure from Northstar Customer Survey 2026",
      "Searched the evidence library",
      "Read 4 evidence passages",
    ]);
    expect(view.steps[1].detail).toBe("10 passages found");
    expect(view.steps.every((s) => !s.failed)).toBe(true);
  });

  it("keeps codes and ids out of every plain-language field", () => {
    const visible = [view.modeReason, view.verification?.label, view.verification?.summary, ...view.steps.flatMap((s) => [s.label, s.detail])];
    for (const text of visible) expect(text ?? "").not.toMatch(RAW_CODE);
    expect(view.technical.runId).toBe(researchRun.run_id);
  });

  it("is not unavailable, cancelled or failed", () => {
    expect(view.modelUnavailable).toBe(false);
    expect(view.cancelled).toBe(false);
    expect(view.failed).toBe(false);
    expect(view.notices).toEqual([]);
  });

  it("falls back to the bare step label when the dataset title is unknown", () => {
    expect(toSavedRunView(researchRun, null).steps[2].label).toBe("Computed a figure");
  });
});

describe("toSavedRunView (standard run fbffdd6b)", () => {
  const view = toSavedRunView(standardRun, null);
  it("has no research steps and names the explicit choice", () => {
    expect(view.mode).toBe(mode("standard"));
    expect(view.modeReason).toBe(`You chose ${mode("standard")}.`);
    expect(view.steps).toEqual([]);
    expect(view.verification).toBeNull();
  });
});

describe("degraded runs", () => {
  const degraded: RunRecord = {
    ...standardRun,
    termination_state: "generation_unavailable",
    degradation_flags: ["LLM_SYNTHESIS_UNAVAILABLE", "LLM_SYNTHESIS_UNAVAILABLE", "NOT_A_KNOWN_FLAG"],
  };

  it("labels the evidence-only fallback, de-duplicates notices and drops unknown codes", () => {
    const view = toSavedRunView(degraded, null);
    expect(view.modelUnavailable).toBe(true);
    expect(view.verification?.label).toBe(terminationState("generation_unavailable").label);
    expect(view.notices.map((n) => n.label)).toEqual(["Live model unavailable"]);
  });

  it("maps verification dispositions", () => {
    const v = (d: RunVerification["final_disposition"]): RunVerification => ({ run_id: "r", final_disposition: d, attempts: [] });
    expect(verificationLabel(standardRun, v("accepted"))?.label).toBe(verificationDisposition("accepted").label);
    expect(verificationLabel(standardRun, v("accepted"))).toMatchObject({ label: "Citations verified", summary: "Citations verified" });
    expect(verificationLabel(standardRun, v("fallback"))?.label).toBe(verificationDisposition("fallback").label);
    expect(verificationLabel(standardRun, v("regenerate"))?.label).toBe(verificationDisposition("regenerate").label);
    expect(verificationLabel(standardRun, v("repaired"))?.label).toBe(verificationDisposition("repaired").label);
  });

  it("labels a citation-check fallback without blaming the model", () => {
    const fallback: RunRecord = { ...standardRun, termination_state: "generation_unavailable", degradation_flags: ["CITATION_VERIFICATION_FAILED"] };
    const view = toSavedRunView(fallback, null);
    expect(view.modelUnavailable).toBe(false);
    expect(view.verification).toMatchObject({ label: verificationDisposition("fallback").label, summary: "Citation checks failed; evidence shown instead" });
  });

  it("flags cancelled and failed runs", () => {
    expect(toSavedRunView({ ...standardRun, status: "cancelled", termination_state: "cancelled" }, null).cancelled).toBe(true);
    expect(toSavedRunView({ ...standardRun, status: "failed", termination_state: "error" }, null).failed).toBe(true);
  });
});

describe("describeModeDecision", () => {
  it("handles unknown and missing reasons", () => {
    expect(describeModeDecision({ requested: "auto", decided: "standard", reason: "zzz" }, "standard")).toBe(
      `${mode("auto")} mode chose ${mode("standard")}.`,
    );
    expect(describeModeDecision({}, "standard")).toBeNull();
  });
});

describe("conversationOutcome", () => {
  const rows = (featured as { items: ConversationSummary[] }).items;
  it("marks completed featured conversations as answered", () => {
    expect(rows.map((r) => conversationOutcome(r)?.label)).toEqual(rows.map(() => "Answered"));
  });
  it("marks evidence-only, cancelled and unanswered rows", () => {
    const base = rows[0];
    const run = base.last_run!;
    const unavailable = { ...base, last_run: { ...run, termination_state: "generation_unavailable", degradation_flags: ["LLM_SYNTHESIS_UNAVAILABLE"] } };
    const fallback = { ...base, last_run: { ...run, termination_state: "generation_unavailable", degradation_flags: ["CITATION_VERIFICATION_FAILED"] } };
    const noEvidence = { ...base, last_run: { ...run, termination_state: "no_relevant_evidence" } };
    expect(conversationOutcome(unavailable)?.label).toBe(terminationState("generation_unavailable").label);
    expect(conversationOutcome(fallback)?.label).toBe(verificationDisposition("fallback").label);
    expect(conversationOutcome(noEvidence)?.label).toBe(terminationState("no_relevant_evidence").label);
    expect(conversationOutcome({ ...base, last_run: { ...run, status: "cancelled", termination_state: "cancelled" } })?.label).toBe("Cancelled");
    expect(conversationOutcome({ ...base, last_run: null })).toBeNull();
  });
  it("counts only answered rows for the Answered filter", () => {
    const base = rows[0];
    const run = base.last_run!;
    expect(rows.every(isAnsweredConversation)).toBe(true);
    expect(isAnsweredConversation({ ...base, last_run: { ...run, termination_state: "completed_with_limited_evidence" } })).toBe(true);
    expect(isAnsweredConversation({ ...base, last_run: { ...run, termination_state: "generation_unavailable", degradation_flags: [] } })).toBe(false);
    expect(isAnsweredConversation({ ...base, last_run: { ...run, status: "failed", termination_state: "error" } })).toBe(false);
    expect(isAnsweredConversation({ ...base, last_run: null })).toBe(false);
  });
});

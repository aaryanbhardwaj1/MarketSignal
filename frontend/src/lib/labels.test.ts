import { describe, expect, it } from "vitest";
import { PRODUCT_ERROR_CODES } from "./api/contracts";
import {
  DEGRADATION_FLAGS,
  INTEGRITY,
  OPPORTUNITY_STATUSES,
  ROUTE_REASONS,
  RUN_MODES,
  SOURCE_CLASSES,
  SOURCE_TYPES,
  STOP_REASONS,
  TERMINATION_STATES,
  TOOL_STEPS,
  UNKNOWN_LABEL,
  VERIFICATION_DISPOSITIONS,
  VERIFICATION_FAILURES,
  degradationFlag,
  errorMessage,
  opportunityStatus,
  terminationState,
  toolStep,
} from "./labels";

// Every enum value seen in the backend and the audits (see the header of labels.ts).
const ENUMS: Record<string, [Record<string, unknown>, string[]]> = {
  flags: [
    DEGRADATION_FLAGS,
    [
      "EVIDENCE_EMPTY", "LLM_SYNTHESIS_UNAVAILABLE", "MODEL_REFUSAL", "GENERATION_TRUNCATED",
      "CITATION_VERIFICATION_FAILED", "PACK_BUDGET_TRUNCATED", "SOURCE_DELETED_DURING_RUN", "RUN_TIMEOUT",
      "RETRIEVAL_TIMEOUT", "RETRIEVAL_LEXICAL_FALLBACK", "RETRIEVAL_DENSE_UNAVAILABLE", "RERANKER_UNAVAILABLE",
      "CONVERSATION_STATE_NOT_UPDATED", "RESEARCH_UNAVAILABLE", "AGENT_STEP_BUDGET_EXHAUSTED",
      "AGENT_TOKEN_BUDGET_EXHAUSTED", "AGENT_CONTEXT_LIMIT", "GATHER_TIMEOUT", "AGENT_REPEAT_CALL_STOPPED",
      "TOOL_CIRCUIT_OPEN", "PLANNER_UNAVAILABLE_FALLBACK", "PLANNER_NO_TOOL_FALLBACK", "AGENT_LLM_UNAVAILABLE",
    ],
  ],
  termination: [
    TERMINATION_STATES,
    [
      "cancelled", "timeout", "tool_failure", "no_relevant_evidence", "generation_unavailable",
      "retrieval_degraded", "completed_with_limited_evidence", "completed", "interrupted", "error",
    ],
  ],
  dispositions: [VERIFICATION_DISPOSITIONS, ["accepted", "repaired", "regenerate", "rejected", "fallback"]],
  failures: [
    VERIFICATION_FAILURES,
    [
      "answer_missing", "answer_too_long", "no_citations", "too_many_citations", "gaps_missing", "verifier_error",
      "unknown_alias", "leak", "dangling_reference", "numbers_in_gaps", "numbers_not_in_cited_evidence",
      "numbers_not_in_pack", "uncited_claim", "uncited_numbers_not_in_pack", "unsupported_clause_removed",
    ],
  ],
  sourceClasses: [SOURCE_CLASSES, ["internal", "customer", "competitor", "market", "financial"]],
  sourceTypes: [SOURCE_TYPES, ["pdf", "docx", "pptx", "xlsx", "csv", "markdown", "text"]],
  routeReasons: [
    ROUTE_REASONS,
    ["explicit_request", "auto_cues", "auto_no_cue", "persona_default", "persona_auto_cues", "persona_auto_no_cue", "analytics_task"],
  ],
  tools: [
    TOOL_STEPS,
    ["search_evidence", "search_evidence_keyword", "get_evidence", "list_sources", "aggregate", "describe_dataset", "filter_rows", "group_compare"],
  ],
  modes: [RUN_MODES, ["auto", "standard", "research"]],
  stopReasons: [
    STOP_REASONS,
    [
      "finish_research", "end_turn", "step_limit", "tool_limit", "token_limit", "context_limit", "time_limit",
      "repeat_call", "tool_errors", "pool_full", "planner_unavailable", "no_successful_search", "llm_unavailable",
    ],
  ],
  opportunities: [OPPORTUNITY_STATUSES, ["supported", "mixed_evidence", "emerging", "needs_research"]],
  integrity: [INTEGRITY, ["verified", "partial", "unverified", "stale", "withdrawn"]],
};

describe("labels", () => {
  it.each(Object.entries(ENUMS))("maps every %s value", (_name, [dict, values]) => {
    const missing = values.filter((v) => !(v in dict));
    expect(missing).toEqual([]);
  });

  it("maps every product error code from the frozen contract", () => {
    for (const code of PRODUCT_ERROR_CODES) expect(errorMessage(code).known, code).toBe(true);
  });

  it("never leaks a code into a label", () => {
    for (const [dict] of Object.values(ENUMS)) {
      for (const entry of Object.values(dict as Record<string, { label: string }>)) {
        expect(entry.label).not.toMatch(/[A-Z]{2,}_[A-Z]/);
        expect(entry.label).not.toMatch(/_/);
      }
    }
  });

  it("falls back to 'Other' for unknown codes, keeping the code for Technical details", () => {
    const h = degradationFlag("SOME_NEW_FLAG");
    expect(h).toEqual({ label: UNKNOWN_LABEL, code: "SOME_NEW_FLAG", known: false });
    expect(terminationState(null).label).toBe(UNKNOWN_LABEL);
    expect(errorMessage("WEIRD").label).toBe("Something went wrong. Try again.");
    expect(errorMessage("WEIRD").code).toBe("WEIRD");
  });

  it("does not treat Object.prototype keys as known codes", () => {
    expect(toolStep("constructor").known).toBe(false);
    expect(toolStep("toString").label).toBe(UNKNOWN_LABEL);
  });

  it("applies the plan's status semantics", () => {
    expect(opportunityStatus("supported").tone).toBe("success");
    expect(opportunityStatus("mixed_evidence").tone).toBe("warn");
    expect(opportunityStatus("emerging").tone).toBe("info");
    expect(opportunityStatus("needs_research").tone).toBe("neutral");
    expect(terminationState("cancelled").tone).toBe("neutral");
    expect(terminationState("completed").tone).toBe("success");
    expect(toolStep("search_evidence").label).toBe("Searched the Evidence Library");
  });
});

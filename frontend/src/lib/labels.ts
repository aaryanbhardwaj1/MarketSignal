/**
 * Plain-language labels for backend codes. Business pages show `label` (and `description`);
 * the raw `code` belongs only inside a "Technical details" disclosure or on Developer Tools pages.
 * Unknown codes humanize to "Other" with `known: false` so the UI never invents a meaning.
 *
 * Enum sources: backend runs/flags.py, agent/state.py, runs/router.py, tools/contracts.py,
 * domain/enums.py, generation/verifier.py, migration 0004, and lib/api/contracts.ts.
 */
import type { StatusTone } from "@/components/ui/tone";
import type { RunPhase } from "./run-stream";

export interface LabelEntry {
  label: string;
  description?: string;
  tone?: StatusTone;
  /**
   * Implementation detail with no business meaning. Business pages (Research details, run
   * notices) skip it; Telemetry and "Technical details" still show it.
   */
  internal?: boolean;
}

export interface Humanized extends LabelEntry {
  code: string;
  known: boolean;
}

export const UNKNOWN_LABEL = "Other";

type Dict = Readonly<Record<string, LabelEntry>>;

function lookup(dict: Dict, code: string | null | undefined): Humanized {
  const key = code ?? "";
  const hit = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : undefined;
  return hit ? { ...hit, code: key, known: true } : { label: UNKNOWN_LABEL, code: key, known: false };
}

/** Run degradation flags (runs/flags.py, agent STOP_FLAGS, retrieval flags). */
export const DEGRADATION_FLAGS: Dict = {
  EVIDENCE_EMPTY: { label: "No matching evidence", description: "The search found no evidence passages for this question.", tone: "warn" },
  LLM_SYNTHESIS_UNAVAILABLE: { label: "Live model unavailable", description: "The answer could not be written by the model, so only the evidence found is shown.", tone: "warn" },
  MODEL_REFUSAL: { label: "Model declined to answer", description: "The model declined to write an answer for this question.", tone: "warn" },
  GENERATION_TRUNCATED: { label: "Answer cut short", description: "The answer reached its length limit before it finished.", tone: "warn" },
  CITATION_VERIFICATION_FAILED: { label: "Citations could not be verified", description: "The answer did not pass citation checks, so a fallback answer is shown.", tone: "warn" },
  PACK_BUDGET_TRUNCATED: { label: "Some evidence left out", description: "More evidence matched than fits in one answer; the strongest passages were used.", tone: "info" },
  SOURCE_DELETED_DURING_RUN: { label: "A source was removed during research", description: "A source was deleted while the answer was being prepared.", tone: "warn" },
  RUN_TIMEOUT: { label: "Research timed out", description: "The run reached its time limit.", tone: "warn" },
  RETRIEVAL_TIMEOUT: { label: "Search timed out", description: "The evidence search reached its time limit.", tone: "warn" },
  RETRIEVAL_LEXICAL_FALLBACK: { label: "Keyword search only", description: "Meaning-based search was unavailable, so keyword search was used.", tone: "warn" },
  RETRIEVAL_DENSE_UNAVAILABLE: { label: "Meaning-based search unavailable", description: "Only keyword matching was available for this search.", tone: "warn" },
  RERANKER_UNAVAILABLE: { label: "Result re-ranking unavailable", description: "Results were ordered without the re-ranking step.", tone: "info", internal: true },
  CONVERSATION_STATE_NOT_UPDATED: { label: "Conversation summary not saved", description: "The answer was saved, but the conversation summary was not updated.", tone: "info", internal: true },
  RESEARCH_UNAVAILABLE: { label: "Research mode unavailable", description: "Research mode was requested but was not available, so Standard mode answered.", tone: "warn" },
  AGENT_STEP_BUDGET_EXHAUSTED: { label: "Research step limit reached", description: "Research stopped after the maximum number of steps.", tone: "warn" },
  AGENT_TOKEN_BUDGET_EXHAUSTED: { label: "Research budget reached", description: "Research stopped after reaching its processing budget.", tone: "warn" },
  AGENT_CONTEXT_LIMIT: { label: "Research context limit reached", description: "Research stopped because it gathered as much context as it can hold.", tone: "warn" },
  GATHER_TIMEOUT: { label: "Research timed out", description: "Evidence gathering reached its time limit.", tone: "warn" },
  AGENT_REPEAT_CALL_STOPPED: { label: "Repeated research step stopped", description: "Research stopped a step that repeated an earlier one.", tone: "info", internal: true },
  TOOL_CIRCUIT_OPEN: { label: "Research tools failing", description: "Research stopped after several research steps failed.", tone: "warn" },
  PLANNER_UNAVAILABLE_FALLBACK: { label: "Research planning unavailable", description: "The live model could not plan research steps, so a standard evidence search was used.", tone: "warn" },
  PLANNER_NO_TOOL_FALLBACK: { label: "No research steps succeeded", description: "No research search succeeded, so a standard evidence search was used.", tone: "warn" },
  AGENT_LLM_UNAVAILABLE: { label: "Live model unavailable for research", description: "Research planning could not reach the live model.", tone: "warn" },
  TOOLS_TRANSPORT_FALLBACK: { label: "Research tools ran locally", description: "Research tools ran in-process instead of through the tool service.", tone: "info", internal: true },
};

/** Run termination states (migration 0004 CHECK constraint, runs/flags.py PRECEDENCE). */
export const TERMINATION_STATES: Dict = {
  completed: { label: "Completed", tone: "success" },
  completed_with_limited_evidence: { label: "Completed with limited evidence", tone: "warn" },
  retrieval_degraded: { label: "Completed with reduced search", tone: "warn" },
  generation_unavailable: { label: "Evidence only (live model unavailable)", tone: "warn" },
  no_relevant_evidence: { label: "No relevant evidence found", tone: "neutral" },
  tool_failure: { label: "Research step failed", tone: "danger" },
  timeout: { label: "Timed out", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  interrupted: { label: "Interrupted", tone: "neutral" },
  error: { label: "Failed", tone: "danger" },
};

/** Run status column (migration 0004). */
export const RUN_STATUSES: Dict = {
  running: { label: "Running", tone: "info" },
  completed: { label: "Completed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  interrupted: { label: "Interrupted", tone: "neutral" },
};

/** Verification dispositions (contracts `Disposition`). */
export const VERIFICATION_DISPOSITIONS: Dict = {
  accepted: { label: "Citations verified", description: "Every citation was checked against the evidence.", tone: "success" },
  repaired: { label: "Verified after corrections", description: "Unsupported statements or citations were removed before the answer was shown.", tone: "success" },
  regenerate: { label: "Rewritten after checks", description: "The first draft failed citation checks and was rewritten.", tone: "warn" },
  rejected: { label: "Did not pass checks", description: "The draft failed citation checks.", tone: "danger" },
  fallback: { label: "Fallback answer", description: "Citation checks failed, so a conservative evidence-only answer is shown.", tone: "warn" },
};

/** Verifier failure categories and rejection reasons (generation/verifier.py). */
export const VERIFICATION_FAILURES: Dict = {
  answer_missing: { label: "Answer section missing" },
  answer_too_long: { label: "Answer too long" },
  no_citations: { label: "No citations" },
  too_many_citations: { label: "Too many citations" },
  gaps_missing: { label: "Evidence gaps not stated" },
  verifier_error: { label: "Check could not run" },
  unknown_alias: { label: "Citation to unknown evidence" },
  leak: { label: "Internal text removed" },
  dangling_reference: { label: "Reference without evidence" },
  numbers_in_gaps: { label: "Figures in an evidence gap" },
  numbers_not_in_cited_evidence: { label: "Figure not in cited evidence" },
  numbers_not_in_pack: { label: "Figure not in the evidence" },
  uncited_claim: { label: "Uncited statement" },
  uncited_numbers_not_in_pack: { label: "Uncited figure not in the evidence" },
  unsupported_clause_removed: { label: "Unsupported statement removed" },
};

/** API, tool and run error codes, as user-facing messages. */
export const ERROR_CODES: Dict = {
  NETWORK_ERROR: { label: "Could not reach the MarketSignal service. Check your connection and try again." },
  UNKNOWN_ERROR: { label: "Something went wrong. Try again." },
  VALIDATION_ERROR: { label: "The request was not valid." },
  NOT_FOUND: { label: "That item could not be found." },
  CONVERSATION_NOT_FOUND: { label: "That conversation could not be found." },
  RUN_NOT_FOUND: { label: "That research run could not be found." },
  DATASET_NOT_FOUND: { label: "That dataset could not be found." },
  ANALYSIS_NOT_FOUND: { label: "That analysis could not be found." },
  EVAL_RUN_NOT_FOUND: { label: "That evaluation run could not be found." },
  EVAL_CATALOG_UNAVAILABLE: { label: "The evaluation catalog is not available in this build." },
  RESULT_NOT_FOUND: { label: "That computed result could not be found." },
  EVIDENCE_NOT_FOUND: { label: "That evidence passage could not be found." },
  SOURCE_NOT_FOUND: { label: "That source could not be found." },
  WORKSPACE_NOT_FOUND: { label: "That workspace could not be found." },
  SOURCE_DELETED: { label: "This source has been withdrawn from the workspace." },
  MALFORMED_HANDLE: { label: "That evidence reference is not valid." },
  PROVIDER_UNAVAILABLE: { label: "The live model is unavailable. Saved answers and evidence are still available." },
  LLM_SYNTHESIS_UNAVAILABLE: { label: "The live model is unavailable, so only the evidence found is shown." },
  DB_UNAVAILABLE: { label: "The data store is temporarily unavailable. Try again shortly." },
  EMBEDDER_UNAVAILABLE: { label: "Meaning-based search is temporarily unavailable." },
  POLICY_DENIED: { label: "This action is not allowed for this workspace." },
  UNAUTHENTICATED: { label: "You need to sign in to do that." },
  TIMEOUT: { label: "The request took too long. Try again." },
  UNAVAILABLE: { label: "The service is temporarily unavailable. Try again shortly." },
  INTERNAL: { label: "Something went wrong on our side. Try again." },
  RUN_FAILED: { label: "The research run failed." },
  RUN_INTERRUPTED: { label: "The research run was interrupted." },
  RUN_TIMEOUT: { label: "The research run timed out." },
  WORKSPACE_EXISTS: { label: "A workspace with that code already exists." },
  FILE_TOO_LARGE: { label: "The file is too large." },
  CONTENT_TOO_LARGE: { label: "The content is too large." },
  UNSUPPORTED_TYPE: { label: "That file type is not supported." },
  METHOD_NOT_ALLOWED: { label: "That action is not supported." },
  HTTP_ERROR: { label: "The request failed." },
};

/** Source classes (domain/enums.py SourceClass). */
export const SOURCE_CLASSES: Dict = {
  internal: { label: "Internal" },
  customer: { label: "Customer research" },
  competitor: { label: "Competitor" },
  market: { label: "Market research" },
  financial: { label: "Financial" },
};

/** Source types (domain/enums.py SourceType). */
export const SOURCE_TYPES: Dict = {
  pdf: { label: "PDF" },
  docx: { label: "Word document" },
  pptx: { label: "Presentation" },
  xlsx: { label: "Spreadsheet" },
  csv: { label: "Data table (CSV)" },
  markdown: { label: "Document" },
  text: { label: "Text" },
};

/** Router reasons (runs/router.py Reason). */
export const ROUTE_REASONS: Dict = {
  explicit_request: { label: "You chose this mode" },
  auto_cues: { label: "The question called for deeper research" },
  auto_no_cue: { label: "The question did not need deeper research" },
  persona_default: { label: "Default for this role" },
  persona_auto_cues: { label: "The question called for deeper research (role default: automatic)" },
  persona_auto_no_cue: { label: "The question did not need deeper research (role default: automatic)" },
  analytics_task: { label: "The question needed computed figures" },
};

/** Research tool names (tools/contracts.py ToolName) as research-step phrases. */
export const TOOL_STEPS: Dict = {
  search_evidence: { label: "Searched the Evidence Library" },
  search_evidence_keyword: { label: "Searched for exact terms" },
  get_evidence: { label: "Read an evidence passage" },
  list_sources: { label: "Reviewed available sources" },
  describe_dataset: { label: "Reviewed a dataset" },
  aggregate: { label: "Computed a figure" },
  filter_rows: { label: "Filtered dataset rows" },
  group_compare: { label: "Compared groups" },
};

/** Live research phases (SSE `status.phase`). "analyzing" is evidence-pack assembly, not analytics. */
export const PHASE_LABELS: Readonly<Record<RunPhase, string>> = {
  routing: "Choosing a mode",
  planning: "Planning research",
  searching: "Searching evidence",
  analyzing: "Selecting evidence",
  synthesizing: "Writing the answer",
  verifying: "Checking citations",
};

/** Name for a deterministic analytics result cited in an answer ("Computed figure 2"). */
export const COMPUTED_FIGURE = "Computed figure";
export const COMPUTED_FIGURES = "Computed figures";

/** Run modes (requested and used). */
export const RUN_MODES: Dict = {
  auto: { label: "Automatic" },
  standard: { label: "Standard" },
  research: { label: "Research" },
};

/** Agent stop reasons (agent/state.py StopReason). */
export const STOP_REASONS: Dict = {
  finish_research: { label: "Research complete", tone: "success" },
  end_turn: { label: "Research complete", tone: "success" },
  pool_full: { label: "Enough evidence gathered", tone: "success" },
  step_limit: { label: "Step limit reached", tone: "warn" },
  tool_limit: { label: "Step limit reached", tone: "warn" },
  token_limit: { label: "Budget reached", tone: "warn" },
  context_limit: { label: "Context limit reached", tone: "warn" },
  time_limit: { label: "Time limit reached", tone: "warn" },
  repeat_call: { label: "Stopped a repeated step", tone: "warn" },
  tool_errors: { label: "Research steps failed", tone: "danger" },
  planner_unavailable: { label: "Planning unavailable", tone: "warn" },
  no_successful_search: { label: "No search succeeded", tone: "warn" },
  llm_unavailable: { label: "Live model unavailable", tone: "warn" },
};

/** Growth-opportunity statuses (contracts `OpportunityStatus`). */
export const OPPORTUNITY_STATUSES: Dict = {
  supported: { label: "Supported", tone: "success" },
  mixed_evidence: { label: "Mixed evidence", tone: "warn" },
  emerging: { label: "Emerging", tone: "info" },
  needs_research: { label: "Needs research", tone: "neutral" },
};

/** Evidence and item integrity (contracts `Integrity` and `ItemIntegrity`). */
export const INTEGRITY: Dict = {
  verified: { label: "Verified", tone: "success" },
  partial: { label: "Partly verified", tone: "warn" },
  unverified: { label: "Unverified", tone: "neutral" },
  stale: { label: "Source updated since", tone: "warn" },
  withdrawn: { label: "Source withdrawn", tone: "danger" },
};

/** Why live generation is unavailable (contracts `GenerationUnavailableReason`). */
export const GENERATION_UNAVAILABLE_REASONS: Dict = {
  DISABLED: { label: "Live model turned off for this environment" },
  NOT_CONFIGURED: { label: "Live model not configured" },
  PROVIDER_REJECTED: { label: "Live model provider unavailable" },
};

/** Notes recorded with a computed result (tools/analytics_contracts.py warnings). */
export const RESULT_WARNINGS: Dict = {
  EMPTY_SELECTION: { label: "No records matched the filters" },
  ZERO_DENOMINATOR: { label: "No eligible records, so the figure could not be computed" },
  NULLS_EXCLUDED: { label: "Empty cells were left out of the calculation" },
  GROUPS_TRUNCATED: { label: "Only the largest groups are shown" },
};

export const degradationFlag = (code: string | null | undefined) => lookup(DEGRADATION_FLAGS, code);
export const terminationState = (code: string | null | undefined) => lookup(TERMINATION_STATES, code);
export const runStatus = (code: string | null | undefined) => lookup(RUN_STATUSES, code);
export const verificationDisposition = (code: string | null | undefined) => lookup(VERIFICATION_DISPOSITIONS, code);
export const verificationFailure = (code: string | null | undefined) => lookup(VERIFICATION_FAILURES, code);
export const sourceClass = (code: string | null | undefined) => lookup(SOURCE_CLASSES, code);
export const sourceType = (code: string | null | undefined) => lookup(SOURCE_TYPES, code);
export const routeReason = (code: string | null | undefined) => lookup(ROUTE_REASONS, code);
export const toolStep = (code: string | null | undefined) => lookup(TOOL_STEPS, code);
export const runMode = (code: string | null | undefined) => lookup(RUN_MODES, code);
export const stopReason = (code: string | null | undefined) => lookup(STOP_REASONS, code);
export const opportunityStatus = (code: string | null | undefined) => lookup(OPPORTUNITY_STATUSES, code);
export const integrity = (code: string | null | undefined) => lookup(INTEGRITY, code);
/** Spreadsheet and CSV sources, by code ("csv", "xlsx") or by their display label. */
export function isTabularSource(typeOrLabel: string | null | undefined): boolean {
  if (!typeOrLabel) return false;
  return ["csv", "xlsx"].some((code) => typeOrLabel === code || typeOrLabel === SOURCE_TYPES[code].label);
}

export const resultWarning = (code: string | null | undefined) => lookup(RESULT_WARNINGS, code);

/** Degradation flags worth showing on business pages (drops `internal` and unknown codes). */
export function userFacingFlags(codes: readonly string[] | null | undefined): Humanized[] {
  return (codes ?? []).map(degradationFlag).filter((f) => f.known && !f.internal);
}

export const generationUnavailableReason = (code: string | null | undefined) =>
  lookup(GENERATION_UNAVAILABLE_REASONS, code);

/** User-facing message for an error code; unknown codes get a generic message, never the code. */
export function errorMessage(code: string | null | undefined): Humanized {
  const hit = lookup(ERROR_CODES, code);
  return hit.known ? hit : { ...hit, label: "Something went wrong. Try again." };
}

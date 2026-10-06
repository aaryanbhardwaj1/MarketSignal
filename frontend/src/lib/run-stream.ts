/**
 * Pure fold of a run's SSE events into UI state (plan §21, ADR-0008).
 *
 * The server persists every event with a per-run `seq` and replays `seq > Last-Event-ID` when the
 * native EventSource reconnects, so the reducer must be idempotent: any event whose `seq` is not
 * greater than the last applied one is dropped. `done` is terminal; nothing after it is applied.
 * `final` is the source of truth and replaces the streamed draft entirely.
 */
import type { AnyCitationCard } from "./api/types";

export const RUN_EVENT_TYPES = [
  "run_started",
  "status",
  "tool_started",
  "tool_completed",
  "evidence",
  "token",
  "citation",
  "warning",
  "draft_reset",
  "final",
  "error",
  "done",
] as const;
export type RunEventType = (typeof RUN_EVENT_TYPES)[number];

export const RUN_PHASES = [
  "routing",
  "planning",
  "searching",
  "analyzing",
  "synthesizing",
  "verifying",
] as const;
export type RunPhase = (typeof RUN_PHASES)[number];

/** Alias binding received in a `citation` event (draft-only; final uses canonical cards). */
export interface AliasCitation {
  alias: string;
  handle: string;
  source_title: string;
  source_class: string;
  locator_label: string;
}

/** `[R#]` alias binding for a computed result, announced by a `citation` event with kind "result". */
export interface ResultAliasCitation {
  kind: "result";
  alias: string;
  result_id: string;
  source_code: string;
  dataset: string;
  op: string;
  summary: string;
}

export type AnyAliasCitation = AliasCitation | ResultAliasCitation;

export const ROUTE_MODES = ["standard", "research"] as const;
export type RouteMode = (typeof ROUTE_MODES)[number];

/** Router decision from `run_started.route` (ADR-0015). Absent for older runs. */
export interface RunRoute {
  /** What the user asked for: `auto`, `standard` or `research`. */
  requested: string;
  personaDefault: string;
  decided: RouteMode;
  /** Deterministic server-authored reason code (never model text). */
  reason: string;
  cues: string[];
}

export const TOOL_KINDS = ["search", "keyword", "lookup", "catalog", "analytics", "other"] as const;
export type ToolKind = (typeof TOOL_KINDS)[number];
export type ToolStatus = "running" | "ok" | "error" | "denied" | "timeout";

/** One research tool call, keyed by (step, callIndex). Only fields of the SSE contract. */
export interface ToolStep {
  step: number;
  callIndex: number;
  tool: string;
  kind: ToolKind;
  /** Deterministic summary; may embed model-supplied text as a quoted string. Plain text only. */
  summary: string;
  status: ToolStatus;
  resultCount: number | null;
  durationMs: number | null;
  errorCode: string | null;
}

/** Defensive bounds: the server caps tool calls at 10 per run. */
export const MAX_TOOL_STEPS = 50;
const MAX_SUMMARY_CHARS = 200;

export interface RunWarning {
  code: string;
  message: string;
}

export interface EvidenceSummary {
  itemCount: number;
  classes: string[];
  truncated: boolean;
}

export interface FinalAnswer {
  message_id: string;
  content: string;
  citations: AnyCitationCard[];
  sections: unknown;
  verification: unknown;
}

export interface RunError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface RunDone {
  terminationState: string;
  flags: string[];
  cacheStatus: string | null;
  timings: Record<string, number>;
}

/** A parsed SSE event: `type` is the SSE event name, `data` the decoded JSON payload. */
export interface RunEvent {
  type: string;
  seq: number;
  data: Record<string, unknown>;
}

export interface RunStreamState {
  lastSeq: number;
  conversationId: string | null;
  route: RunRoute | null;
  /** Research tool calls ordered by (step, callIndex), independent of arrival order. */
  tools: readonly ToolStep[];
  phase: RunPhase | null;
  /** Deterministic, server-authored status text (never model reasoning). */
  statusMessage: string | null;
  /** Generation attempt the draft belongs to; tokens from older attempts are ignored. */
  attempt: number;
  draft: string;
  citationsByAlias: Readonly<Record<string, AnyAliasCitation>>;
  warnings: readonly RunWarning[];
  evidence: EvidenceSummary | null;
  /** Reason of the latest `draft_reset`, if any (e.g. `verification_failed`, `evidence_only`). */
  draftResetReason: string | null;
  final: FinalAnswer | null;
  error: RunError | null;
  done: RunDone | null;
  terminationState: string | null;
}

export const initialRunStreamState: RunStreamState = Object.freeze({
  lastSeq: 0,
  conversationId: null,
  route: null,
  tools: Object.freeze([]),
  phase: null,
  statusMessage: null,
  attempt: 0,
  draft: "",
  citationsByAlias: Object.freeze({}),
  warnings: Object.freeze([]),
  evidence: null,
  draftResetReason: null,
  final: null,
  error: null,
  done: null,
  terminationState: null,
}) as RunStreamState;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const str = (value: unknown, fallback = ""): string => (typeof value === "string" ? value : fallback);
const num = (value: unknown, fallback = 0): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;
const strList = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];

function isCard(value: unknown): value is AnyCitationCard {
  if (!isRecord(value)) return false;
  if (value.kind === "result") return typeof value.result_id === "string" && value.result_id.length > 0;
  return typeof value.handle === "string" && value.handle.length > 0;
}

/**
 * Validates the citation array of a `final` event or a stored message (drops malformed cards).
 * Evidence cards need a handle (older stored cards have no `kind`); result cards need a result_id.
 */
export function parseCards(value: unknown): AnyCitationCard[] {
  return Array.isArray(value) ? value.filter(isCard) : [];
}

/**
 * Decodes one SSE message. Returns null for undecodable JSON or a payload without a positive
 * integer `seq` (falling back to the SSE `id`), so the reducer only ever sees well-formed events.
 */
export function parseRunEvent(type: string, rawData: string, lastEventId?: string): RunEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(rawData);
  } catch {
    return null;
  }
  if (!isRecord(data)) return null;
  const seq = typeof data.seq === "number" ? data.seq : Number(lastEventId);
  if (!Number.isInteger(seq) || seq < 1) return null;
  return { type, seq, data };
}

function parseRoute(value: unknown): RunRoute | null {
  if (!isRecord(value)) return null;
  const decided = str(value.decided);
  if (!(ROUTE_MODES as readonly string[]).includes(decided)) return null;
  return {
    requested: str(value.requested),
    personaDefault: str(value.persona_default),
    decided: decided as RouteMode,
    reason: str(value.reason),
    cues: strList(value.cues),
  };
}

const TOOL_STATUSES = ["ok", "error", "denied", "timeout"] as const;
const optNum = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
const nonNegInt = (value: unknown): number | null =>
  typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;

/**
 * Upserts a tool call by (step, call_index) so `tool_started`/`tool_completed` merge into one row
 * whichever arrives first, then keeps the list sorted. Events without a valid step are ignored.
 */
function applyToolEvent(
  state: RunStreamState,
  data: Record<string, unknown>,
  completed: boolean,
): RunStreamState {
  const step = nonNegInt(data.step);
  if (step === null) return state;
  const callIndex = nonNegInt(data.call_index) ?? 0;
  const existing = state.tools.find((t) => t.step === step && t.callIndex === callIndex);
  if (!existing && state.tools.length >= MAX_TOOL_STEPS) return state;

  const base: ToolStep = existing ?? {
    step,
    callIndex,
    tool: "",
    kind: "other",
    summary: "",
    status: "running",
    resultCount: null,
    durationMs: null,
    errorCode: null,
  };
  const tool = str(data.tool) || base.tool;
  let next: ToolStep;
  if (completed) {
    const status = str(data.status);
    next = {
      ...base,
      tool,
      status: (TOOL_STATUSES as readonly string[]).includes(status) ? (status as ToolStatus) : "error",
      resultCount: optNum(data.result_count),
      durationMs: optNum(data.duration_ms),
      errorCode: str(data.error_code) || null,
    };
  } else {
    const kind = str(data.kind);
    next = {
      ...base,
      tool,
      kind: (TOOL_KINDS as readonly string[]).includes(kind) ? (kind as ToolKind) : "other",
      summary: str(data.summary).slice(0, MAX_SUMMARY_CHARS),
    };
  }
  const tools = [...state.tools.filter((t) => t !== existing), next].sort(
    (a, b) => a.step - b.step || a.callIndex - b.callIndex,
  );
  return { ...state, tools };
}

function applyToken(state: RunStreamState, data: Record<string, unknown>): RunStreamState {
  const attempt = num(data.attempt, state.attempt);
  const text = str(data.text);
  if (attempt < state.attempt || !text) return state;
  if (attempt > state.attempt) {
    return { ...state, attempt, draft: text, citationsByAlias: {} };
  }
  return { ...state, draft: state.draft + text };
}

function parseAliasCitation(data: Record<string, unknown>): AnyAliasCitation | null {
  const alias = str(data.alias);
  if (!alias) return null;
  if (data.kind === "result") {
    const resultId = str(data.result_id);
    if (!resultId) return null;
    return {
      kind: "result",
      alias,
      result_id: resultId,
      source_code: str(data.source_code),
      dataset: str(data.dataset),
      op: str(data.op),
      summary: str(data.summary),
    };
  }
  const handle = str(data.handle);
  if (!handle) return null;
  return {
    alias,
    handle,
    source_title: str(data.source_title, handle),
    source_class: str(data.source_class),
    locator_label: str(data.locator_label),
  };
}

function applyCitation(state: RunStreamState, data: Record<string, unknown>): RunStreamState {
  const attempt = num(data.attempt, state.attempt);
  const citation = parseAliasCitation(data);
  if (attempt < state.attempt || !citation) return state;
  const alias = citation.alias;
  const fresh = attempt > state.attempt;
  return {
    ...state,
    attempt,
    draft: fresh ? "" : state.draft,
    citationsByAlias: { ...(fresh ? {} : state.citationsByAlias), [alias]: citation },
  };
}

/**
 * `draft_reset` discards the current draft and its alias bindings. Its `attempt` names the next
 * attempt for a regeneration (e.g. 2) or 0 for the evidence-only fallback, so the accepted
 * attempt moves past the discarded one either way and late tokens from it stay ignored.
 */
function applyDraftReset(state: RunStreamState, data: Record<string, unknown>): RunStreamState {
  const attempt = Math.max(num(data.attempt, 0), state.attempt + 1);
  return {
    ...state,
    attempt,
    draft: "",
    citationsByAlias: {},
    draftResetReason: str(data.reason) || null,
  };
}

function applyFinal(state: RunStreamState, data: Record<string, unknown>): RunStreamState {
  const final: FinalAnswer = {
    message_id: str(data.message_id),
    content: str(data.content),
    citations: parseCards(data.citations),
    sections: data.sections ?? null,
    verification: data.verification ?? null,
  };
  return { ...state, final, draft: "", citationsByAlias: {} };
}

function applyDone(state: RunStreamState, data: Record<string, unknown>): RunStreamState {
  const timings: Record<string, number> = {};
  if (isRecord(data.timings)) {
    for (const [key, value] of Object.entries(data.timings)) {
      if (typeof value === "number" && Number.isFinite(value)) timings[key] = value;
    }
  }
  const terminationState = str(data.termination_state, "completed");
  const done: RunDone = {
    terminationState,
    flags: strList(data.flags),
    cacheStatus: typeof data.cache_status === "string" ? data.cache_status : null,
    timings,
  };
  return { ...state, done, terminationState, phase: null, statusMessage: null };
}

function applyEvent(state: RunStreamState, event: RunEvent): RunStreamState {
  const { data } = event;
  switch (event.type as RunEventType) {
    case "run_started":
      return {
        ...state,
        conversationId: str(data.conversation_id) || state.conversationId,
        route: parseRoute(data.route) ?? state.route,
      };
    case "status": {
      const phase = str(data.phase);
      return {
        ...state,
        phase: (RUN_PHASES as readonly string[]).includes(phase) ? (phase as RunPhase) : state.phase,
        statusMessage: str(data.message) || state.statusMessage,
      };
    }
    case "evidence":
      return {
        ...state,
        evidence: {
          itemCount: num(data.item_count),
          classes: strList(data.classes),
          truncated: data.truncated === true,
        },
      };
    case "token":
      return applyToken(state, data);
    case "citation":
      return applyCitation(state, data);
    case "warning": {
      // One notice per code: a run can repeat a warning (e.g. withheld draft text after a
      // source was deleted) and the UI must not render a flood of identical notices.
      const code = str(data.code, "WARNING");
      if (state.warnings.some((w) => w.code === code)) return state;
      return { ...state, warnings: [...state.warnings, { code, message: str(data.message) }] };
    }
    case "draft_reset":
      return applyDraftReset(state, data);
    case "final":
      return applyFinal(state, data);
    case "error":
      return {
        ...state,
        error: {
          code: str(data.code, "RUN_ERROR"),
          message: str(data.message, "The run failed."),
          retryable: data.retryable === true,
        },
      };
    case "done":
      return applyDone(state, data);
    case "tool_started":
      return applyToolEvent(state, data, false);
    case "tool_completed":
      return applyToolEvent(state, data, true);
    default:
      return state; // unknown event types are ignored (forward compatible)
  }
}

/** Folds one event into the state. Duplicate / replayed `seq`s and anything after `done` are no-ops. */
export function reduceRunEvent(state: RunStreamState, event: RunEvent): RunStreamState {
  if (state.done || event.seq <= state.lastSeq) return state;
  return { ...applyEvent(state, event), lastSeq: event.seq };
}

export function foldRunEvents(events: readonly RunEvent[], state = initialRunStreamState): RunStreamState {
  return events.reduce(reduceRunEvent, state);
}

export const TERMINATION_LABELS: Readonly<Record<string, string>> = {
  completed: "Completed",
  completed_with_limited_evidence: "Completed with limited evidence",
  retrieval_degraded: "Retrieval degraded",
  generation_unavailable: "Answer generation unavailable",
  no_relevant_evidence: "No relevant evidence",
  tool_failure: "A retrieval step failed",
  timeout: "Timed out",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
};

export function terminationLabel(state: string): string {
  return TERMINATION_LABELS[state] ?? state.replace(/_/g, " ");
}

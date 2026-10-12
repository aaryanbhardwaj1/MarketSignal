import { ApiError } from "./api/errors";

/** Every signal that a live model was not available for an answer or a new question. */
export interface ModelAvailabilitySignals {
  /** Run warnings (SSE `warning` events) as codes or `{ code }` objects. */
  warnings?: readonly (string | { code: string })[];
  terminationState?: string | null;
  /** Run degradation flags and research flags. */
  flags?: readonly string[];
  /** `sections.reason` of an evidence-only answer. */
  sectionsReason?: string | null;
  /** An error thrown by `POST /runs` (or any API call). */
  httpError?: unknown;
}

const UNAVAILABLE_WARNING = "LLM_SYNTHESIS_UNAVAILABLE";
const UNAVAILABLE_TERMINATION = "generation_unavailable";
const UNAVAILABLE_FLAGS: ReadonlySet<string> = new Set([
  "LLM_SYNTHESIS_UNAVAILABLE",
  "PLANNER_UNAVAILABLE_FALLBACK",
  "AGENT_LLM_UNAVAILABLE",
]);
export const PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE";

/** True for the API's 503 `PROVIDER_UNAVAILABLE` (new runs refused while the model is off). */
export function isProviderUnavailableError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503 && error.code === PROVIDER_UNAVAILABLE;
}

/** Whether any of the five signals says the live model was unavailable. */
export function isModelUnavailable(signals: ModelAvailabilitySignals): boolean {
  const warned = (signals.warnings ?? []).some(
    (w) => (typeof w === "string" ? w : w.code) === UNAVAILABLE_WARNING,
  );
  return (
    warned ||
    signals.terminationState === UNAVAILABLE_TERMINATION ||
    (signals.flags ?? []).some((flag) => UNAVAILABLE_FLAGS.has(flag)) ||
    signals.sectionsReason === UNAVAILABLE_WARNING ||
    isProviderUnavailableError(signals.httpError)
  );
}

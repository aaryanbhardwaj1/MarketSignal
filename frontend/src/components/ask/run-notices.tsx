import { Callout } from "@/components/ui/callout";
import { DevDetails } from "@/components/ui/disclosure";
import { degradationFlag, terminationState } from "@/lib/labels";
import { isModelUnavailable } from "@/lib/model-availability";
import type { RunDone, RunError, RunWarning } from "@/lib/run-stream";
import { MODEL_UNAVAILABLE_BODY } from "./model-unavailable";

/**
 * Plain-language notices for a live run: errors, an unusual ending and degradation flags.
 * Codes and raw warning text appear only inside "Technical details".
 */
export function RunNotices({
  warnings,
  done,
  error,
}: {
  warnings: readonly RunWarning[];
  done: RunDone | null;
  error: RunError | null;
}) {
  const termination = done && done.terminationState !== "completed" ? done.terminationState : null;
  const flags = done?.flags ?? [];
  if (!warnings.length && !flags.length && !termination && !error) return null;

  const unavailable = isModelUnavailable({ warnings, terminationState: termination, flags });
  const ending = termination ? terminationState(termination) : null;
  const flagLabels = [
    ...new Set(
      flags
        .map((f) => degradationFlag(f))
        .filter((l) => !l.internal)
        .map((l) => (l.known ? l.label : "A processing notice was recorded")),
    ),
  ];
  const technical = {
    error: error ? { code: error.code, message: error.message } : undefined,
    termination: termination ?? undefined,
    warnings: warnings.length ? warnings : undefined,
    flags: flags.length ? flags : undefined,
  };

  return (
    <div className="flex flex-col gap-2">
      {error && !unavailable && (
        <Callout tone="danger" title="This question could not be completed">
          Something went wrong while preparing the answer.{error.retryable ? " You can ask again." : ""}
        </Callout>
      )}
      {unavailable && (
        <Callout tone="warn" title="Live model unavailable">
          {MODEL_UNAVAILABLE_BODY}
        </Callout>
      )}
      {!unavailable && ending && termination !== "cancelled" && (
        <p className="text-sm text-secondary">
          Ended: <span className="font-medium text-primary">{ending.known ? ending.label : "Ended early"}</span>
        </p>
      )}
      {flagLabels.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-secondary" aria-label="Run notices">
          {flagLabels.map((label) => (
            <li key={label}>{label}</li>
          ))}
        </ul>
      )}
      <DevDetails data={technical} />
    </div>
  );
}

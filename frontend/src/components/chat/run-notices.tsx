import { humanize } from "@/lib/format";
import { terminationLabel, type RunDone, type RunError, type RunWarning } from "@/lib/run-stream";

/** Small, factual notices about a run: warnings, done flags, non-completed termination, errors. */
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

  return (
    <div className="flex flex-col gap-1.5 text-xs">
      {error && (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-red-900">
          <code className="font-mono font-semibold">{error.code}</code> {error.message}
          {error.retryable && <span className="text-red-700"> (you can retry)</span>}
        </p>
      )}
      {termination && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-amber-900">
          Run ended: <span className="font-medium">{terminationLabel(termination)}</span>{" "}
          <code className="font-mono text-amber-700">({termination})</code>
        </p>
      )}
      {warnings.length > 0 && (
        <ul className="flex flex-col gap-1" aria-label="Run warnings">
          {warnings.map((w, i) => (
            <li key={`${w.code}-${i}`} className="rounded-md bg-amber-50/70 px-2.5 py-1 text-amber-900">
              <code className="font-mono font-semibold">{w.code}</code>
              {w.message && <span>: {w.message}</span>}
            </li>
          ))}
        </ul>
      )}
      {flags.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-slate-500">
          Flags:
          {flags.map((flag) => (
            <code
              key={flag}
              title={humanize(flag)}
              className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700"
            >
              {flag}
            </code>
          ))}
        </p>
      )}
    </div>
  );
}

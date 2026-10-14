import { Check, Minus, X } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { PulseNode } from "./pulse-node";

export type StageState = "pending" | "active" | "done" | "skipped" | "failed";

export interface Stage {
  id: string;
  label: ReactNode;
  /** One short line under the label (what this stage does or found). */
  detail?: ReactNode;
  state: StageState;
  /** Right-aligned timing text, e.g. "1.2 s" or "running". Rendered with tabular numerals. */
  timing?: ReactNode;
}

/** Screen-reader wording for each state; exported for tests and other summaries. */
export const STAGE_STATE_LABEL: Record<StageState, string> = {
  pending: "Not started",
  active: "In progress",
  done: "Done",
  skipped: "Skipped",
  failed: "Failed",
};

/** Progress summary such as "3 of 5 stages done". Pure; exported for tests. */
export function stageSummary(stages: readonly Stage[]): string {
  const done = stages.filter((s) => s.state === "done" || s.state === "skipped").length;
  const failed = stages.some((s) => s.state === "failed");
  const base = `${done} of ${stages.length} stages done`;
  return failed ? `${base}, one failed` : base;
}

function Marker({ state }: { state: StageState }) {
  const ring = "flex h-4 w-4 shrink-0 items-center justify-center rounded-full";
  switch (state) {
    case "done":
      return (
        <span className={cx(ring, "bg-accent text-white")}>
          <Check aria-hidden className="h-2.5 w-2.5" strokeWidth={3} />
        </span>
      );
    case "failed":
      return (
        <span className={cx(ring, "bg-danger text-white")}>
          <X aria-hidden className="h-2.5 w-2.5" strokeWidth={3} />
        </span>
      );
    case "skipped":
      return (
        <span className={cx(ring, "border border-border-strong bg-surface text-muted")}>
          <Minus aria-hidden className="h-2.5 w-2.5" strokeWidth={2.5} />
        </span>
      );
    case "active":
      return (
        <span className={cx(ring, "border border-accent bg-accent-subtle")}>
          <PulseNode size="sm" />
        </span>
      );
    default:
      return <span className={cx(ring, "border border-border-strong bg-surface")} />;
  }
}

const LABEL_TONE: Record<StageState, string> = {
  pending: "text-muted",
  active: "font-medium text-primary",
  done: "text-primary",
  skipped: "text-muted line-through decoration-border-strong",
  failed: "font-medium text-danger",
};

/** Connector below a stage: filled (accent) once the stage is behind us. */
function filled(state: StageState): boolean {
  return state === "done" || state === "skipped";
}

/**
 * Observable stages of a long operation (research run, analytics execution, deck generation).
 * Vertical by default; `orientation="horizontal"` is a compact single-row variant without detail
 * lines. The active stage carries `aria-current="step"`; every state is spelled out for screen
 * readers, never conveyed by colour or icon alone.
 */
export function StageProgress({
  stages,
  orientation = "vertical",
  label = "Progress",
  className,
}: {
  stages: readonly Stage[];
  orientation?: "vertical" | "horizontal";
  label?: string;
  className?: string;
}) {
  if (orientation === "horizontal") {
    return (
      <ol aria-label={label} className={cx("flex items-start", className)}>
        {stages.map((stage, i) => {
          const last = i === stages.length - 1;
          return (
            <li key={stage.id} aria-current={stage.state === "active" ? "step" : undefined} className={cx("flex min-w-0 flex-col gap-1.5", !last && "flex-1")}>
              <div className="flex items-center">
                <Marker state={stage.state} />
                {!last && (
                  <span aria-hidden className="relative mx-1.5 h-px flex-1 bg-border">
                    {filled(stage.state) && <span className="ms-connector-fill-x absolute inset-0 bg-accent" />}
                  </span>
                )}
              </div>
              <span className={cx("truncate pr-2 text-xs", LABEL_TONE[stage.state])}>
                {stage.label}
                <span className="sr-only">: {STAGE_STATE_LABEL[stage.state]}</span>
              </span>
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <ol aria-label={label} className={cx("flex flex-col", className)}>
      {stages.map((stage, i) => {
        const last = i === stages.length - 1;
        return (
          <li key={stage.id} aria-current={stage.state === "active" ? "step" : undefined} className="relative flex gap-3">
            <div className="flex flex-col items-center pt-0.5">
              <Marker state={stage.state} />
              {!last && (
                <span aria-hidden className="relative my-1 w-px flex-1 bg-border">
                  {filled(stage.state) && <span className="ms-connector-fill absolute inset-0 bg-accent" />}
                </span>
              )}
            </div>
            <div className={cx("flex min-w-0 flex-1 items-start justify-between gap-3", !last && "pb-4")}>
              <div className="min-w-0">
                <p className={cx("text-sm", LABEL_TONE[stage.state])}>
                  {stage.label}
                  <span className="sr-only">: {STAGE_STATE_LABEL[stage.state]}</span>
                </p>
                {stage.detail && <p className="mt-0.5 text-xs text-muted">{stage.detail}</p>}
              </div>
              {stage.timing && <span className="shrink-0 text-xs text-muted tabular-nums">{stage.timing}</span>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

import { cx } from "@/lib/cx";
import { COMPUTED_FIGURE } from "@/lib/labels";
import { CLAIM_DEFINITION } from "./claim-tag";
import { Tooltip } from "./tooltip";

export type CiteState = "verified" | "unverified" | "stale";

const KIND = {
  evidence:
    "bg-cite-evidence-bg text-cite-evidence border-cite-evidence/15 hover:border-cite-evidence/45 hover:bg-accent-muted active:bg-accent-muted",
  result: "bg-cite-result-bg text-cite-result border-cite-result/15 hover:border-cite-result/45",
} as const;

const STATE_TEXT: Record<CiteState, string | null> = {
  verified: null,
  unverified: "not verified",
  stale: "source updated",
};

/**
 * Inline citation: a compact, slightly raised numbered pill. Evidence chips show a number;
 * computed-result chips show "Computed N". Hover or keyboard focus shows the source title in a
 * tooltip; activating it opens the evidence drawer (`onOpen`) and never navigates away.
 * Non-verified state is spelled out, not only signalled by the dashed outline.
 */
export function CiteChip({
  kind,
  index,
  label,
  state = "verified",
  onOpen,
}: {
  kind: "evidence" | "result";
  index: number;
  label: string;
  state?: CiteState;
  onOpen: () => void;
}) {
  const stateText = STATE_TEXT[state];
  const visible = kind === "evidence" ? String(index) : `Computed ${index}`;
  const a11y = `${kind === "evidence" ? `Evidence ${index}` : `${COMPUTED_FIGURE} ${index}`}: ${label}${stateText ? ` (${stateText})` : ""}`;
  return (
    <span className="mx-0.5 inline-flex align-baseline">
      <Tooltip content={stateText ? `${label} (${stateText})` : label}>
        <button
          type="button"
          onClick={onOpen}
          aria-label={a11y}
          className={cx(
            "relative -top-0.5 inline-flex h-4 min-w-4 items-center justify-center gap-1 rounded-sm border px-1 text-2xs font-semibold leading-none tabular-nums",
            "transition-colors duration-(--duration-fast) ease-standard",
            KIND[kind],
            state !== "verified" && "border-dashed",
          )}
        >
          {visible}
          {stateText && <span className="font-normal opacity-80">· {stateText}</span>}
        </button>
      </Tooltip>
    </span>
  );
}

/** Same definition as the section-level Inference tag, so both read identically. */
export const INFERENCE_DESCRIPTION = CLAIM_DEFINITION.inference;

/** Marks a sentence as the assistant's inference rather than a cited fact. */
export function InferenceTag() {
  return (
    <span
      title={INFERENCE_DESCRIPTION}
      className="mx-0.5 inline-flex h-4 items-center rounded-sm border border-dashed border-claim-inference/50 bg-claim-inference-bg/60 px-1 align-baseline text-2xs font-medium leading-none text-claim-inference"
    >
      Inference
      <span className="sr-only">: {INFERENCE_DESCRIPTION.toLowerCase()}</span>
    </span>
  );
}

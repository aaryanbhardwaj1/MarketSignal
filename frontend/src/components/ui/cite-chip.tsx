import { cx } from "@/lib/cx";

export type CiteState = "verified" | "unverified" | "stale";

const KIND = {
  evidence: "bg-cite-evidence-bg text-cite-evidence border-cite-evidence/20 hover:border-cite-evidence/50",
  result: "bg-cite-result-bg text-cite-result border-cite-result/20 hover:border-cite-result/50",
} as const;

const STATE_TEXT: Record<CiteState, string | null> = {
  verified: null,
  unverified: "not verified",
  stale: "source updated",
};

/**
 * Inline citation. Evidence chips show a number; computed-result chips show "Computed".
 * Opens the evidence drawer (`onOpen`); never navigates away. State is spelled out, not only coloured.
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
  const a11y = `${kind === "evidence" ? `Evidence ${index}` : `Computed result ${index}`}: ${label}${stateText ? ` (${stateText})` : ""}`;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={a11y}
      title={label}
      className={cx(
        "mx-0.5 inline-flex h-5 min-w-5 items-center justify-center gap-1 rounded-sm border px-1 align-baseline text-xs font-medium tabular-nums transition-colors",
        KIND[kind],
        state !== "verified" && "border-dashed",
      )}
    >
      {visible}
      {stateText && <span className="font-normal opacity-80">· {stateText}</span>}
    </button>
  );
}

/** Marks a sentence as the assistant's inference rather than a cited fact. */
export function InferenceTag() {
  return (
    <span className="mx-0.5 inline-flex items-center rounded-sm border border-dashed border-border-strong px-1 align-baseline text-xs text-cite-inference">
      Inference
    </span>
  );
}

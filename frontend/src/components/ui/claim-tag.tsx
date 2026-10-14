import { cx } from "@/lib/cx";
import { Tooltip } from "./tooltip";

/** Product-wide claim types (grounding contract). Labels are exact and never paraphrased. */
export type ClaimType = "observed" | "derived" | "inference" | "hypothesis" | "forecast";

export const CLAIM_LABEL: Record<ClaimType, string> = {
  observed: "Observed",
  derived: "Derived",
  inference: "Inference",
  hypothesis: "Hypothesis",
  forecast: "Forecast",
};

export const CLAIM_DEFINITION: Record<ClaimType, string> = {
  observed: "Stated directly by a cited source passage.",
  derived: "Computed from the data by the deterministic analytics engine.",
  inference: "An interpretation supported by the evidence but not stated by it.",
  hypothesis: "A forward-looking proposition to test, not an established fact.",
  forecast: "A projection stated by a cited source, not an observed fact.",
};

/** Solid outline for what was observed or computed; dashed for anything interpretive or forward-looking. */
const STYLE: Record<ClaimType, string> = {
  observed: "border-solid border-claim-observed/20 bg-claim-observed-bg text-claim-observed",
  derived: "border-solid border-claim-derived/20 bg-claim-derived-bg text-claim-derived",
  inference: "border-dashed border-claim-inference/50 bg-claim-inference-bg/60 text-claim-inference",
  hypothesis: "border-dashed border-claim-hypothesis/50 bg-claim-hypothesis-bg/60 text-claim-hypothesis",
  forecast: "border-dashed border-claim-forecast/50 bg-claim-forecast-bg/60 text-claim-forecast",
};

const SIZE = { sm: "h-4.5 px-1.5 text-2xs", md: "h-5 px-1.5 text-xs" } as const;

/**
 * Labels what kind of claim a statement is. With `explain`, keyboard focus or hover shows the
 * one-line definition (linked with aria-describedby); without it the definition is still in the
 * accessible name, so the tag never relies on colour or line style alone.
 */
export function ClaimTag({
  type,
  size = "md",
  explain = false,
  className,
}: {
  type: ClaimType;
  size?: keyof typeof SIZE;
  explain?: boolean;
  className?: string;
}) {
  const tag = (
    <span
      tabIndex={explain ? 0 : undefined}
      data-claim={type}
      className={cx(
        "inline-flex shrink-0 items-center whitespace-nowrap rounded-md border align-baseline font-medium normal-case leading-none tracking-normal",
        SIZE[size],
        STYLE[type],
        explain && "cursor-help",
        className,
      )}
    >
      {CLAIM_LABEL[type]}
      {!explain && <span className="sr-only">: {CLAIM_DEFINITION[type]}</span>}
    </span>
  );
  return explain ? <Tooltip content={CLAIM_DEFINITION[type]}>{tag}</Tooltip> : tag;
}

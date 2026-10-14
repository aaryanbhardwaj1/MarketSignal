"use client";

import { useCapabilities } from "@/lib/api/hooks/core";
import { cx } from "@/lib/cx";
import { Tooltip } from "../ui/tooltip";

export const MODEL_AVAILABLE = "Live model available";
export const MODEL_UNAVAILABLE = "Live model unavailable";
export const MODEL_UNAVAILABLE_DETAIL = "Live model unavailable — saved research, evidence, analytics and insights still work";
const MODEL_CHECKING = "Checking live model";

type ModelState = "checking" | "available" | "unavailable";

/** Live generation state; anything other than an explicit "available" counts as unavailable. */
export function useModelState(): ModelState {
  const capabilities = useCapabilities();
  if (capabilities.isPending) return "checking";
  return capabilities.data?.generation?.available ? "available" : "unavailable";
}

const DOT: Record<ModelState, string> = {
  checking: "bg-text-disabled",
  available: "bg-success",
  unavailable: "bg-text-muted",
};

/**
 * Small status dot for the top bar. The short state is the accessible name; the tooltip adds
 * what still works when the live model is off. Treated as unavailable until the API says
 * otherwise, including when the capabilities endpoint cannot be reached.
 */
export function ModelStatusDot() {
  const state = useModelState();
  const label = state === "available" ? MODEL_AVAILABLE : state === "unavailable" ? MODEL_UNAVAILABLE : MODEL_CHECKING;
  const tip = state === "unavailable" ? MODEL_UNAVAILABLE_DETAIL : label;
  return (
    <Tooltip content={tip} side="bottom" decorative={tip === label}>
      <span tabIndex={0} className="inline-flex size-8 items-center justify-center rounded-md" data-state={state}>
        <span aria-hidden className={cx("size-2 rounded-full", DOT[state], state === "available" && "ring-3 ring-success-subtle")} />
        <span className="sr-only">{label}</span>
      </span>
    </Tooltip>
  );
}

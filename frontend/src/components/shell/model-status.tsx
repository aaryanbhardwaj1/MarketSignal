"use client";

import { useCapabilities } from "@/lib/api/hooks/core";
import { generationUnavailableReason } from "@/lib/labels";
import { StatusIndicator } from "../ui/status-indicator";

export const MODEL_AVAILABLE = "Live model available";
export const MODEL_UNAVAILABLE = "Live model unavailable";

/**
 * Footer line for live answer generation. Treated as unavailable until the API says otherwise,
 * including when the capabilities endpoint cannot be reached.
 */
export function ModelStatus() {
  const capabilities = useCapabilities();
  if (capabilities.isPending) {
    return <StatusIndicator tone="neutral" label="Checking live model" className="text-muted" />;
  }
  const generation = capabilities.data?.generation;
  if (generation?.available) return <StatusIndicator tone="success" label={MODEL_AVAILABLE} />;
  const reason = generation?.reason ? generationUnavailableReason(generation.reason) : null;
  return (
    <span title={reason?.known ? reason.label : undefined}>
      <StatusIndicator tone="neutral" label={MODEL_UNAVAILABLE} />
    </span>
  );
}

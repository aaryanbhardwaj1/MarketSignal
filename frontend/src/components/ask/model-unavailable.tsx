"use client";

import { useSyncExternalStore } from "react";
import { Callout } from "@/components/ui/callout";
import { useCapabilities } from "@/lib/api/hooks/core";
import { useAskSession } from "./ask-session";

export const MODEL_UNAVAILABLE_TITLE = "Live model unavailable";
export const MODEL_UNAVAILABLE_BODY = "Existing insights, saved answers and the Evidence Library remain available.";

const noopSubscribe = () => () => {};

/**
 * False during server rendering and hydration, true afterwards. Capabilities may already be cached
 * on the client (the sidebar footer reads them), so anything decided from them must wait until
 * after hydration or the first client render would differ from the server's.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

/** Whether new questions can be asked right now (capabilities and any 503 from a start). */
export function useGenerationAvailable(): { available: boolean; pending: boolean } {
  const hydrated = useHydrated();
  const capabilities = useCapabilities();
  const { providerUnavailable } = useAskSession();
  if (!hydrated) return { available: false, pending: true };
  if (providerUnavailable) return { available: false, pending: false };
  if (capabilities.isPending) return { available: false, pending: true };
  // If capabilities cannot be read, allow asking; a 503 on start still switches to the calm state.
  return { available: capabilities.data?.generation.available ?? true, pending: false };
}

export function ModelUnavailableCallout() {
  return (
    <Callout tone="neutral" title={MODEL_UNAVAILABLE_TITLE}>
      {MODEL_UNAVAILABLE_BODY}
    </Callout>
  );
}

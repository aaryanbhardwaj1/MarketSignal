"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { Callout } from "@/components/ui/callout";
import { useCapabilities } from "@/lib/api/hooks/core";
import { askHref } from "@/lib/routes";
import { useAskSession } from "./ask-session";

export const MODEL_UNAVAILABLE_TITLE = "Live model unavailable";
export const MODEL_UNAVAILABLE_BODY = "Existing insights, saved answers and the Evidence Library remain available.";
/** One calm line under the composer while new questions cannot be answered. */
export const MODEL_UNAVAILABLE_INLINE = "Live model unavailable — saved research, evidence, analytics and insights still work.";
/** Anchor of the saved-research strip on the empty Chat page. */
export const SAVED_RESEARCH_ANCHOR = "saved-research";

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

/** Inline offline notice for the composer, linking to the saved research on the Chat start page. */
export function ModelUnavailableInline({ ws }: { ws: string }) {
  return (
    <p role="status" className="flex flex-wrap items-center gap-x-2 px-1 text-sm text-muted">
      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-text-disabled" />
      <span>{MODEL_UNAVAILABLE_INLINE}</span>
      <Link href={`${askHref(ws)}#${SAVED_RESEARCH_ANCHOR}`} className="font-medium text-accent-text hover:underline">
        Open saved research
      </Link>
    </p>
  );
}

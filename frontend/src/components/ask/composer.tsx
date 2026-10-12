"use client";

import { Callout } from "@/components/ui/callout";
import { Skeleton } from "@/components/ui/states";
import { useCapabilities } from "@/lib/api/hooks/core";
import { useAskSession } from "./ask-session";
import { QuestionForm } from "./question-form";

export const MODEL_UNAVAILABLE_TITLE = "Live model unavailable";
export const MODEL_UNAVAILABLE_BODY =
  "Existing workspace insights, saved research and evaluation data remain available.";

/** Whether new questions can be asked right now (capabilities and any 503 from a start). */
export function useGenerationAvailable(): { available: boolean; pending: boolean } {
  const capabilities = useCapabilities();
  const { providerUnavailable } = useAskSession();
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

/** Question composer. Disabled with a calm notice while the live model is unavailable. */
export function Composer({ conversationId }: { conversationId: string | null }) {
  const session = useAskSession();
  const { available, pending } = useGenerationAvailable();
  if (pending) return <Skeleton height="7rem" />;
  return (
    <div className="flex flex-col gap-2">
      {!available && <ModelUnavailableCallout />}
      {available && session.startError ? (
        <Callout tone="danger" title="The question could not be started">
          Please try again in a moment.
        </Callout>
      ) : null}
      <QuestionForm
        key={session.prefill.nonce}
        initialText={session.prefill.text}
        initialMode={session.prefill.mode}
        disabled={!available || session.running}
        busy={session.starting}
        onSubmit={(question, mode) => session.ask(question, mode, conversationId)}
      />
    </div>
  );
}

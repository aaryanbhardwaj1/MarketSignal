"use client";

import { Callout } from "@/components/ui/callout";
import { Skeleton } from "@/components/ui/states";
import { useAskSession } from "./ask-session";
import { ModelUnavailableCallout, useGenerationAvailable } from "./model-unavailable";
import { QuestionForm } from "./question-form";

export { MODEL_UNAVAILABLE_BODY, MODEL_UNAVAILABLE_TITLE, ModelUnavailableCallout, useGenerationAvailable } from "./model-unavailable";

/** Question composer. Disabled with a calm notice while the live model is unavailable. */
export function Composer({ conversationId }: { conversationId: string | null }) {
  const session = useAskSession();
  const { available, pending } = useGenerationAvailable();
  // Same markup on the server and in the first client render (see useGenerationAvailable).
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
        autoFocus={session.prefill.focus}
        onAutoFocused={session.composerFocused}
        disabled={!available}
        locked={session.running}
        busy={session.starting}
        onSubmit={(question, mode) => session.ask(question, mode, conversationId)}
      />
    </div>
  );
}

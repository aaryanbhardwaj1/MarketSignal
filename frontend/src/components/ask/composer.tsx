"use client";

import { useNewChatSignal } from "@/components/shell/new-chat-signal";
import { Callout } from "@/components/ui/callout";
import { Skeleton } from "@/components/ui/states";
import { useAskSession } from "./ask-session";
import { AttachmentChips } from "./attachments/attachment-chips";
import { useAttachments } from "./attachments/attachments-context";
import { ModelUnavailableInline, useGenerationAvailable } from "./model-unavailable";
import { QuestionForm } from "./question-form";

export {
  MODEL_UNAVAILABLE_BODY,
  MODEL_UNAVAILABLE_INLINE,
  MODEL_UNAVAILABLE_TITLE,
  ModelUnavailableCallout,
  useGenerationAvailable,
} from "./model-unavailable";

export const ATTACHMENT_HINT =
  "Attached files are added to this workspace's evidence and become searchable once processed. Answers draw on all workspace evidence.";

/**
 * Floating question composer (Chat start page and conversation view). While the live model is
 * unavailable, sending is disabled with one calm line; attaching files still works because
 * processing does not need the model.
 */
export function Composer({ conversationId }: { conversationId: string | null }) {
  const session = useAskSession();
  const attachments = useAttachments();
  const { available, pending } = useGenerationAvailable();

  // "New chat" in the shell: empty draft, no attachments, focus in the box.
  useNewChatSignal(() => {
    attachments.clear();
    session.fillComposer("");
  });

  // Same markup on the server and in the first client render (see useGenerationAvailable).
  if (pending) return <Skeleton height="7rem" />;
  return (
    <div className="flex flex-col gap-2">
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
        attachments={<AttachmentChips items={attachments.items} onRemove={attachments.remove} />}
        onAttach={attachments.add}
        onSubmit={async (question, mode) => {
          const accepted = await session.ask(question, mode, conversationId);
          if (accepted) attachments.clearSettled();
          return accepted;
        }}
      />
      {!available ? (
        <ModelUnavailableInline ws={session.ws} />
      ) : attachments.items.length > 0 ? (
        <p className="px-1 text-sm text-muted">{ATTACHMENT_HINT}</p>
      ) : null}
    </div>
  );
}

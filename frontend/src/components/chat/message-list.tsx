import type { ReactNode } from "react";
import type { ChatMessage } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { parseCards } from "@/lib/run-stream";
import { Badge } from "../ui/badge";
import { AnswerView } from "./answer-view";

const REDACTION_NOTE =
  "This answer was removed because a source it cited was deleted from the workspace.";

export function UserBubble({ children, timestamp }: { children: ReactNode; timestamp?: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-sm whitespace-pre-wrap break-words text-white shadow-sm">
        {children}
        {timestamp && <p className="mt-1 text-right text-[10px] text-indigo-200">{formatDateTime(timestamp)}</p>}
      </div>
    </div>
  );
}

export function AssistantCard({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {children}
      {footer && <div className="mt-3 border-t border-slate-100 pt-2">{footer}</div>}
    </div>
  );
}

function AssistantMessage({ ws, message }: { ws: string; message: ChatMessage }) {
  if (message.status === "redacted") {
    return (
      <AssistantCard>
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500 italic">
          <Badge tone="muted">Redacted</Badge>
          {message.content || REDACTION_NOTE}
        </div>
      </AssistantCard>
    );
  }
  const statusBadge =
    message.status === "complete" ? null : (
      <Badge tone={message.status === "failed" ? "danger" : "warning"}>{message.status}</Badge>
    );
  return (
    <AssistantCard footer={statusBadge}>
      <AnswerView
        ws={ws}
        content={message.content}
        citations={parseCards(message.citations)}
        sections={message.sections}
      />
    </AssistantCard>
  );
}

/** Stored conversation turns (user bubbles + verified assistant answers). */
export function MessageList({ ws, messages }: { ws: string; messages: readonly ChatMessage[] }) {
  return (
    <>
      {messages.map((message) =>
        message.role === "user" ? (
          <UserBubble key={message.message_id} timestamp={message.created_at}>
            {message.content}
          </UserBubble>
        ) : (
          <AssistantMessage key={message.message_id} ws={ws} message={message} />
        ),
      )}
    </>
  );
}

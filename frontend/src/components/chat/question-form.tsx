"use client";

import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import type { RunMode } from "@/lib/api/types";
import { RUN_MODE_OPTIONS } from "@/lib/run-mode";
import { buttonClass } from "../ui/form-controls";

export const MAX_QUESTION_LENGTH = 2000;

export function QuestionForm({
  disabled,
  busy,
  onSubmit,
}: {
  disabled: boolean;
  busy: boolean;
  /** Resolves true when the question was accepted (the box is then cleared). */
  onSubmit: (question: string, mode: RunMode) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<RunMode>("auto");
  const groupId = useId();
  const question = text.trim();
  const canSubmit = !disabled && !busy && question.length > 0;

  const submit = async () => {
    if (!canSubmit) return;
    if (await onSubmit(question, mode)) setText("");
  };

  const onFormSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <form onSubmit={onFormSubmit} className="flex flex-col gap-2">
      <label htmlFor="chat-question" className="sr-only">
        Ask a question about this workspace
      </label>
      <textarea
        id="chat-question"
        rows={3}
        value={text}
        maxLength={MAX_QUESTION_LENGTH}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask a question grounded in this workspace's evidence…"
        className="block w-full resize-y rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
      />
      <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600" disabled={busy}>
        <legend className="sr-only">Answer mode</legend>
        <span aria-hidden className="font-medium text-slate-500">Mode</span>
        {RUN_MODE_OPTIONS.map((option) => (
          <label key={option.value} className="flex items-center gap-1.5">
            <input
              type="radio"
              name={`${groupId}-mode`}
              value={option.value}
              checked={mode === option.value}
              onChange={() => setMode(option.value)}
              aria-describedby={`${groupId}-help-${option.value}`}
              className="h-3.5 w-3.5 border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            {option.label}
          </label>
        ))}
      </fieldset>
      <ul className="flex flex-col gap-0.5 text-[11px] text-slate-400 sm:flex-row sm:gap-x-4">
        {RUN_MODE_OPTIONS.map((option) => (
          <li key={option.value} id={`${groupId}-help-${option.value}`}>
            <span className="font-medium text-slate-500">{option.label}:</span> {option.help}
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-slate-400">
          Enter to send · Shift+Enter for a new line · {text.length}/{MAX_QUESTION_LENGTH}
        </p>
        <button type="submit" className={buttonClass("primary")} disabled={!canSubmit}>
          {busy ? "Starting…" : "Ask"}
        </button>
      </div>
    </form>
  );
}

"use client";

import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import type { RunMode } from "@/lib/api/types";
import { cx } from "@/lib/cx";
import { RUN_MODE_OPTIONS } from "@/lib/run-mode";
import { Button } from "../ui/button";

export const MAX_QUESTION_LENGTH = 2000;

export function QuestionForm({
  disabled,
  busy,
  onSubmit,
  initialText = "",
  initialMode = "auto",
}: {
  disabled: boolean;
  busy: boolean;
  /** Resolves true when the question was accepted (the box is then cleared). */
  onSubmit: (question: string, mode: RunMode) => Promise<boolean>;
  /** Pre-filled question (remount with a new `key` to apply a new one). */
  initialText?: string;
  initialMode?: RunMode;
}) {
  const [text, setText] = useState(initialText);
  const [mode, setMode] = useState<RunMode>(initialMode);
  const groupId = useId();
  const question = text.trim();
  const canSubmit = !disabled && !busy && question.length > 0;
  const selected = RUN_MODE_OPTIONS.find((o) => o.value === mode) ?? RUN_MODE_OPTIONS[0];

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
    <form
      onSubmit={onFormSubmit}
      className={cx(
        "flex flex-col rounded-lg border border-border-strong bg-surface focus-within:border-accent",
        disabled && "bg-surface-muted",
      )}
    >
      <label htmlFor="chat-question" className="sr-only">
        Ask a question about this workspace
      </label>
      <textarea
        id="chat-question"
        rows={3}
        value={text}
        disabled={disabled}
        maxLength={MAX_QUESTION_LENGTH}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask a question about this workspace's customers, competitors or market…"
        className="block w-full resize-none rounded-t-lg bg-transparent px-3 py-2.5 text-base text-primary placeholder:text-muted focus:outline-none disabled:cursor-not-allowed"
      />
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-3 py-2">
        <fieldset className="flex min-w-0 flex-wrap items-center gap-2" disabled={busy || disabled}>
          <legend className="sr-only">Answer mode</legend>
          <span aria-hidden className="text-sm text-muted">
            Mode
          </span>
          <div className="inline-flex rounded-md border border-border bg-surface-muted p-0.5">
            {RUN_MODE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={cx(
                  "relative cursor-pointer rounded-sm px-2.5 py-1 text-sm font-medium has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent",
                  mode === option.value ? "bg-surface text-primary shadow-sm" : "text-secondary hover:text-primary",
                )}
              >
                <input
                  type="radio"
                  name={`${groupId}-mode`}
                  value={option.value}
                  checked={mode === option.value}
                  onChange={() => setMode(option.value)}
                  aria-describedby={`${groupId}-help-${option.value}`}
                  className="sr-only"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="flex items-center gap-3">
          <span className="text-xs tabular-nums text-muted">
            {text.length}/{MAX_QUESTION_LENGTH}
          </span>
          <Button type="submit" disabled={!canSubmit} loading={busy}>
            {busy ? "Starting…" : "Ask"}
          </Button>
        </div>
      </div>
      <p aria-hidden className="border-t border-border px-3 py-1.5 text-sm text-muted">
        <span className="font-medium text-secondary">{selected.label}:</span> {selected.help}
        {!disabled && <span className="hidden lg:inline"> Enter to send, Shift+Enter for a new line.</span>}
      </p>
      <ul className="sr-only">
        {RUN_MODE_OPTIONS.map((option) => (
          <li key={option.value} id={`${groupId}-help-${option.value}`}>
            {option.help}
          </li>
        ))}
      </ul>
    </form>
  );
}

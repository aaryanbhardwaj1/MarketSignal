"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { RunMode } from "@/lib/api/types";
import { cx } from "@/lib/cx";
import { RUN_MODE_OPTIONS } from "@/lib/run-mode";
import { Button } from "../ui/button";
import { Segmented } from "../ui/segmented";

export const MAX_QUESTION_LENGTH = 2000;

export function QuestionForm({
  disabled,
  locked = false,
  busy,
  onSubmit,
  initialText = "",
  initialMode = "auto",
  autoFocus = false,
  onAutoFocused,
}: {
  /** Asking is not possible (live model unavailable): the box is disabled. */
  disabled: boolean;
  /**
   * A question is being answered: the box stays focusable but read-only (aria-disabled), so
   * pressing Enter does not drop keyboard focus to the page body.
   */
  locked?: boolean;
  busy: boolean;
  /** Resolves true when the question was accepted (the box is then cleared). */
  onSubmit: (question: string, mode: RunMode) => Promise<boolean>;
  /** Pre-filled question (remount with a new `key` to apply a new one). */
  initialText?: string;
  initialMode?: RunMode;
  /** Focus the box on mount (after an example question or "Ask again" fills it). */
  autoFocus?: boolean;
  onAutoFocused?: () => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState(initialText);
  const [mode, setMode] = useState<RunMode>(initialMode);
  const groupId = useId();
  const question = text.trim();
  const inactive = disabled || locked;
  const canSubmit = !inactive && !busy && question.length > 0;

  useEffect(() => {
    if (!autoFocus || disabled) return;
    const box = textareaRef.current;
    if (!box) return;
    box.focus();
    box.setSelectionRange(box.value.length, box.value.length);
    onAutoFocused?.();
  }, [autoFocus, disabled, onAutoFocused]);
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
        "flex flex-col rounded-lg border border-border-control bg-surface focus-within:border-accent",
        inactive && "bg-surface-muted",
      )}
    >
      <label htmlFor="chat-question" className="sr-only">
        Ask a question about this workspace
      </label>
      <textarea
        ref={textareaRef}
        id="chat-question"
        rows={3}
        value={text}
        disabled={disabled}
        readOnly={locked}
        aria-disabled={locked || undefined}
        maxLength={MAX_QUESTION_LENGTH}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask a question about this workspace's customers, competitors or market…"
        className="block w-full resize-none rounded-t-lg bg-transparent px-3 py-2.5 text-base text-primary placeholder:text-muted focus:outline-none disabled:cursor-not-allowed aria-disabled:cursor-not-allowed aria-disabled:text-secondary"
      />
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-3 py-2">
        <Segmented
          label="Answer mode"
          visibleLabel="Mode"
          name={`${groupId}-mode`}
          value={mode}
          options={RUN_MODE_OPTIONS.map((option) => ({
            value: option.value,
            label: option.label,
            describedBy: `${groupId}-help-${option.value}`,
          }))}
          onChange={setMode}
          disabled={busy || inactive}
        />
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
        {!inactive && <span className="hidden lg:inline"> Enter to send, Shift+Enter for a new line.</span>}
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

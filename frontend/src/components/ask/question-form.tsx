"use client";

import { ArrowUp, Info, LoaderCircle, Paperclip } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import type { RunMode } from "@/lib/api/types";
import { ATTACHMENT_ACCEPT } from "@/lib/attachments";
import { cx } from "@/lib/cx";
import { RUN_MODE_OPTIONS } from "@/lib/run-mode";
import { IconButton } from "../ui/icon-button";
import { Segmented } from "../ui/segmented";
import { Tooltip } from "../ui/tooltip";

export const MAX_QUESTION_LENGTH = 2000;
/** The character counter appears only once the question gets this close to the limit. */
export const COUNTER_THRESHOLD = 1800;
/** Auto-grow cap: about six lines of text, then the box scrolls. */
const MAX_TEXTAREA_PX = 6 * 22 + 24;

/** Plain-words explanation of each answer mode (tooltip and screen-reader descriptions). */
export const COMPOSER_MODE_HELP: Readonly<Record<RunMode, string>> = {
  auto: "MarketSignal chooses the depth that fits the question.",
  standard: "Fast answer from a single search of the evidence.",
  research: "Deeper, multi-step investigation across sources and analysis tools. Slower.",
};

export interface KeyLike {
  key: string;
  shiftKey: boolean;
  metaKey: boolean;
  ctrlKey: boolean;
  isComposing: boolean;
}

/** Enter or Cmd/Ctrl+Enter sends; Shift+Enter (and anything during IME composition) does not. */
export function composerKeySends(event: KeyLike): boolean {
  if (event.key !== "Enter" || event.isComposing) return false;
  return !event.shiftKey || event.metaKey || event.ctrlKey;
}

export function showCounter(length: number): boolean {
  return length >= COUNTER_THRESHOLD;
}

function ModeHelp() {
  return (
    <span className="flex w-72 flex-col gap-1.5 text-left">
      {RUN_MODE_OPTIONS.map((option) => (
        <span key={option.value}>
          <span className="font-medium">{option.label}:</span> {COMPOSER_MODE_HELP[option.value]}
        </span>
      ))}
    </span>
  );
}

export function QuestionForm({
  disabled,
  locked = false,
  busy,
  onSubmit,
  initialText = "",
  initialMode = "auto",
  autoFocus = false,
  onAutoFocused,
  attachments,
  onAttach,
}: {
  /** Asking is not possible (live model unavailable): the box and send are disabled. */
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
  /** Focus the box on mount (after an example question, "Ask again" or New chat). */
  autoFocus?: boolean;
  onAutoFocused?: () => void;
  /** Attached-file chips, shown above the question box. */
  attachments?: ReactNode;
  /** Files picked with the paperclip. Without it, no attach control is shown. */
  onAttach?: (files: File[]) => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
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

  // Grow with the text up to about six lines.
  useLayoutEffect(() => {
    const box = textareaRef.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, MAX_TEXTAREA_PX)}px`;
  }, [text]);

  const submit = async () => {
    if (!canSubmit) return;
    if (await onSubmit(question, mode)) setText("");
  };

  const onFormSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!composerKeySends({ ...event, isComposing: event.nativeEvent.isComposing })) return;
    event.preventDefault();
    void submit();
  };

  const onFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = ""; // picking the same file again still fires change
    if (files.length > 0) onAttach?.(files);
  };

  return (
    <form
      onSubmit={onFormSubmit}
      className={cx(
        "flex flex-col rounded-float border border-border bg-raised shadow-overlay",
        "transition-[border-color,box-shadow] duration-(--duration-fast) ease-standard focus-within:border-accent-ring",
        disabled && "bg-surface-muted",
      )}
    >
      {attachments}
      <label htmlFor="chat-question" className="sr-only">
        Ask a question about this workspace
      </label>
      <textarea
        ref={textareaRef}
        id="chat-question"
        rows={2}
        value={text}
        disabled={disabled}
        readOnly={locked}
        aria-disabled={locked || undefined}
        maxLength={MAX_QUESTION_LENGTH}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about customers, competitors, markets or your own plans…"
        style={{ maxHeight: MAX_TEXTAREA_PX }}
        className="block w-full resize-none overflow-y-auto bg-transparent px-4 pt-3.5 pb-1 text-md text-primary placeholder:text-muted focus:outline-none disabled:cursor-not-allowed aria-disabled:cursor-not-allowed aria-disabled:text-secondary"
      />
      <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5 pt-1">
        <div className="flex min-w-0 items-center gap-1">
          <Segmented
            label="Answer mode"
            visibleLabel={null}
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
          <Tooltip content={<ModeHelp />} side="top">
            <button
              type="button"
              aria-label="About answer modes"
              className="inline-flex size-7 items-center justify-center rounded-md text-muted hover:bg-surface-muted hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              <Info aria-hidden className="size-3.5" />
            </button>
          </Tooltip>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {showCounter(text.length) && (
            <span className="px-1 text-xs tabular-nums text-muted" aria-live="polite">
              {text.length}/{MAX_QUESTION_LENGTH}
            </span>
          )}
          {onAttach && (
            <>
              <input
                ref={fileRef}
                type="file"
                multiple
                accept={ATTACHMENT_ACCEPT}
                onChange={onFiles}
                className="sr-only"
                tabIndex={-1}
                aria-hidden
              />
              <IconButton
                label="Attach files"
                tooltip="Attach files (PDF, Word, PowerPoint, Excel, CSV, Markdown, text; up to 25 MB). They are added to the workspace evidence."
                tooltipSide="top"
                icon={<Paperclip aria-hidden />}
                onClick={() => fileRef.current?.click()}
              />
            </>
          )}
          <button
            type="submit"
            disabled={!canSubmit}
            aria-label={busy ? "Starting…" : "Send question"}
            className={cx(
              "inline-flex size-8 items-center justify-center rounded-md bg-accent text-white shadow-raised",
              "transition-[background-color,opacity] duration-(--duration-fast) ease-standard hover:bg-accent-hover",
              "disabled:cursor-not-allowed disabled:bg-sunken disabled:text-disabled disabled:shadow-none",
            )}
          >
            {busy ? <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" /> : <ArrowUp aria-hidden className="size-4" />}
          </button>
        </div>
      </div>
      <ul className="sr-only">
        {RUN_MODE_OPTIONS.map((option) => (
          <li key={option.value} id={`${groupId}-help-${option.value}`}>
            {COMPOSER_MODE_HELP[option.value]}
          </li>
        ))}
      </ul>
    </form>
  );
}

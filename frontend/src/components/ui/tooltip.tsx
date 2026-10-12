"use client";

import { cloneElement, isValidElement, useId, useState, type ReactElement, type ReactNode } from "react";

type TriggerProps = {
  "aria-describedby"?: string;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onFocus?: () => void;
  onBlur?: () => void;
};

/**
 * Small description shown on hover and keyboard focus, linked with `aria-describedby`.
 * The child must be a single focusable element. Esc dismisses it.
 */
export function Tooltip({ content, children }: { content: ReactNode; children: ReactElement<TriggerProps> }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  if (!isValidElement(children)) return children;
  const trigger = cloneElement(children, {
    "aria-describedby": id,
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => setOpen(false),
    onFocus: () => setOpen(true),
    onBlur: () => setOpen(false),
  });
  return (
    <span
      className="relative inline-flex"
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      {trigger}
      <span
        id={id}
        role="tooltip"
        hidden={!open}
        className="absolute bottom-full left-1/2 z-30 mb-1.5 w-max max-w-xs -translate-x-1/2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-primary shadow-overlay"
      >
        {content}
      </span>
    </span>
  );
}

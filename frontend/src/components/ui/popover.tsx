"use client";

import {
  cloneElement,
  isValidElement,
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  useState,
  type MouseEvent,
  type ReactElement,
  type ReactNode,
} from "react";
import { cx } from "@/lib/cx";

type TriggerProps = {
  "aria-expanded"?: boolean;
  "aria-controls"?: string;
  "aria-haspopup"?: "dialog" | "menu" | "true";
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void;
};

export type PopoverAlign = "start" | "end";

/**
 * Click-to-open floating panel (disclosure pattern) anchored under its trigger. The trigger
 * child must be a single button; it receives `aria-expanded`/`aria-controls` and a chained click
 * handler. Escape closes and returns focus to the trigger; a pointer press outside, or focus
 * leaving the trigger and panel, closes it. Works controlled (`open` + `onOpenChange`) or not.
 */
export function Popover({
  trigger,
  children,
  open: controlledOpen,
  onOpenChange,
  align = "start",
  label,
  className,
  panelClassName,
}: {
  trigger: ReactElement<TriggerProps>;
  /** Panel body; a function receives `close` for links and actions inside the panel. */
  children: ReactNode | ((close: () => void) => ReactNode);
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  align?: PopoverAlign;
  /** Accessible name of the panel region. */
  label?: string;
  className?: string;
  panelClassName?: string;
}) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = controlledOpen ?? uncontrolledOpen;
  const wrapper = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const setOpen = (next: boolean) => {
    setUncontrolledOpen(next);
    onOpenChange?.(next);
  };
  // Document listeners always see the latest props without re-subscribing.
  const closeFromDocument = useEffectEvent((refocus: boolean) => {
    setOpen(false);
    // The trigger is the wrapper's first child.
    if (refocus) (wrapper.current?.firstElementChild as HTMLElement | null)?.focus();
  });

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) closeFromDocument(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeFromDocument(true);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!isValidElement(trigger)) return null;
  const own = trigger.props;
  const close = () => setOpen(false);
  const button = cloneElement(trigger, {
    "aria-expanded": open,
    "aria-controls": open ? panelId : undefined,
    onClick: (event: MouseEvent<HTMLButtonElement>) => {
      own.onClick?.(event);
      if (!event.defaultPrevented) setOpen(!open);
    },
  });

  return (
    <div
      ref={wrapper}
      className={cx("relative inline-flex", className)}
      onBlur={(event) => {
        // A null relatedTarget (pointer outside, or Safari not focusing a clicked link) is left to
        // the pointerdown handler, so a click on a link inside the panel is never swallowed.
        const next = event.relatedTarget as Node | null;
        if (open && next && !event.currentTarget.contains(next)) setOpen(false);
      }}
    >
      {button}
      {open && (
        <div
          id={panelId}
          role="region"
          aria-label={label}
          className={cx(
            "ms-pop-in absolute top-full z-50 mt-1.5 min-w-56 rounded-float border border-border bg-surface p-1 shadow-overlay",
            align === "end" ? "right-0" : "left-0",
            panelClassName,
          )}
        >
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}

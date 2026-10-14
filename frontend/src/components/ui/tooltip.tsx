"use client";

import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useState,
  type FocusEvent,
  type ReactElement,
  type ReactNode,
} from "react";
import { cx } from "@/lib/cx";

type TriggerProps = {
  "aria-describedby"?: string;
  onFocus?: (event: FocusEvent<HTMLElement>) => void;
  onBlur?: (event: FocusEvent<HTMLElement>) => void;
};

export type TooltipSide = "top" | "bottom" | "left" | "right";

// The padding on the side facing the trigger bridges the gap, so the pointer can move onto the tip.
const SIDE_CLASS: Record<TooltipSide, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 pb-1.5",
  bottom: "top-full left-1/2 -translate-x-1/2 pt-1.5",
  left: "right-full top-1/2 -translate-y-1/2 pr-1.5",
  right: "left-full top-1/2 -translate-y-1/2 pl-1.5",
};

function isKeyboardFocus(el: Element): boolean {
  try {
    return el.matches(":focus-visible");
  } catch {
    return true; // selector unsupported: err on the side of showing the tip
  }
}

/**
 * Small description shown on hover and keyboard focus. The child must be a single focusable
 * element; its own focus/blur handlers and `aria-describedby` are kept and chained. Escape
 * dismisses it (WCAG 1.4.13), and hover is tracked on the wrapper so the pointer can move onto
 * the tip. With `decorative`, the tip only repeats the trigger's accessible name and is hidden
 * from assistive technology (no duplicate announcement).
 */
export function Tooltip({
  content,
  children,
  side = "top",
  decorative = false,
  className,
}: {
  content: ReactNode;
  children: ReactElement<TriggerProps>;
  side?: TooltipSide;
  decorative?: boolean;
  className?: string;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!isValidElement(children)) return children;
  const own = children.props;
  const describedBy = decorative ? own["aria-describedby"] : [own["aria-describedby"], id].filter(Boolean).join(" ");
  const trigger = cloneElement(children, {
    "aria-describedby": describedBy || undefined,
    onFocus: (event: FocusEvent<HTMLElement>) => {
      own.onFocus?.(event);
      // Only keyboard focus opens the tip; a click focusing the trigger must not leave it stuck open.
      if (isKeyboardFocus(event.currentTarget)) setOpen(true);
    },
    onBlur: (event: FocusEvent<HTMLElement>) => {
      own.onBlur?.(event);
      setOpen(false);
    },
  });
  return (
    <span
      className={cx("relative inline-flex", className)}
      onPointerEnter={(event) => {
        if (event.pointerType !== "touch") setOpen(true);
      }}
      onPointerLeave={() => setOpen(false)}
    >
      {trigger}
      <span
        id={id}
        role="tooltip"
        aria-hidden={decorative || undefined}
        hidden={!open}
        className={cx("pointer-events-auto absolute z-50 w-max max-w-xs", SIDE_CLASS[side])}
      >
        <span className="ms-fade-in flex items-center gap-1.5 rounded-md bg-ink px-2 py-1 text-xs font-medium text-white shadow-overlay">
          {content}
        </span>
      </span>
    </span>
  );
}

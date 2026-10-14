"use client";

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { cx } from "@/lib/cx";

/**
 * Shared native-<dialog> behaviour: `showModal()` gives the focus trap and inert background,
 * Esc (the `cancel` event) calls `onClose`, and focus returns to the element that opened it.
 */
function useModal(open: boolean) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
    if (!open && opener.current) {
      opener.current.focus();
      opener.current = null;
    }
  }, [open]);

  useEffect(
    () => () => {
      opener.current?.focus();
    },
    [],
  );

  return ref;
}

function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close"
      className="-mt-1 -mr-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted transition-colors duration-(--duration-fast) ease-standard hover:bg-surface-muted hover:text-primary active:bg-sunken"
    >
      <X aria-hidden size={16} strokeWidth={1.75} />
    </button>
  );
}

/** Full width below 1024px (laptop-first layout); a fixed side panel from `lg` up. */
const DRAWER_WIDTH = { md: "max-w-none lg:max-w-drawer", lg: "max-w-none lg:max-w-content" } as const;

/**
 * Right-hand side panel (evidence, result detail) on a native <dialog>: slides in (`ms-panel-in`
 * via `ms-drawer`), header with title, subtitle and close, a scrolling body and an optional
 * footer slot for the panel's actions.
 */
export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  width = "md",
  footer,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  width?: "md" | "lg";
  footer?: ReactNode;
  children: ReactNode;
}) {
  const ref = useModal(open);
  const titleId = useId();
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className={cx(
        "ms-overlay ms-drawer fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-dvh w-full border-l border-border bg-surface p-0 text-primary shadow-overlay",
        DRAWER_WIDTH[width],
      )}
    >
      {open && (
        <div className="flex h-full flex-col">
          <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-5 pt-4 pb-3.5">
            <div className="min-w-0">
              <h2 id={titleId} className="text-md font-semibold text-primary">
                {title}
              </h2>
              {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
            </div>
            <CloseButton onClose={onClose} />
          </header>
          <div className="ms-scroll min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && (
            <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-border bg-surface px-5 py-3">
              {footer}
            </footer>
          )}
        </div>
      )}
    </dialog>
  );
}

/** Centred modal dialog (confirmations, small forms). */
export function Dialog({
  open,
  onClose,
  title,
  description,
  footer,
  dismissible = true,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  /** When false, Esc does nothing (e.g. while a request is in flight). */
  dismissible?: boolean;
  children?: ReactNode;
}) {
  const ref = useModal(open);
  const titleId = useId();
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        if (dismissible) onClose();
      }}
      className="ms-overlay ms-pop-in m-auto w-full max-w-md rounded-float border border-border bg-surface p-0 text-primary shadow-overlay"
    >
      {open && (
        <>
          <div className="px-5 pt-4 pb-4">
            <h2 id={titleId} className="text-md font-semibold text-primary">
              {title}
            </h2>
            {description && <p className="mt-1 text-base text-secondary">{description}</p>}
            {children && <div className="mt-3 text-base text-primary">{children}</div>}
          </div>
          {footer && (
            <div className="flex justify-end gap-2 border-t border-border bg-canvas px-5 py-3">{footer}</div>
          )}
        </>
      )}
    </dialog>
  );
}

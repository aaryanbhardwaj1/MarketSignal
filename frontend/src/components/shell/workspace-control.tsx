"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { useWorkspaces } from "@/lib/api/hooks/core";
import type { Workspace } from "@/lib/api/types";
import { cx } from "@/lib/cx";
import { Skeleton } from "../ui/states";
import { isTestWorkspace, switchWorkspaceHref } from "./nav";

/** Workspaces a person may switch to: never the test-harness codes. */
export function visibleWorkspaces(workspaces: readonly Workspace[] | undefined): Workspace[] {
  return (workspaces ?? []).filter((w) => !isTestWorkspace(w.code));
}

const CHEVRON = (
  <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth="1.75">
    <path d="m4.5 6.5 3.5 3.5 3.5-3.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/**
 * Shows the current workspace by name; a small popover switches among the visible ones.
 * While the list is loading or unavailable, it degrades to a neutral label (no switching).
 */
export function WorkspaceControl({ ws }: { ws: string }) {
  const pathname = usePathname() ?? "";
  const workspaces = useWorkspaces();
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  const visible = visibleWorkspaces(workspaces.data);
  const current = workspaces.data?.find((w) => w.code === ws);
  const others = visible.filter((w) => w.code !== ws);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (workspaces.isPending) {
    return (
      <div className="px-2 py-1.5" aria-busy="true">
        <span className="sr-only">Loading workspace</span>
        <Skeleton lines={1} />
      </div>
    );
  }

  const name = current?.name ?? (workspaces.isError ? "Workspace unavailable" : "Unknown workspace");

  return (
    <div ref={wrapper} className="relative">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={others.length === 0}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-2 rounded-md border border-border bg-surface-muted px-2.5 py-2 text-left hover:border-border-strong disabled:cursor-default disabled:hover:border-border"
      >
        <span className="min-w-0">
          <span className="sr-only">Current workspace: </span>
          <span className="line-clamp-2 text-sm font-medium text-primary" title={current?.name}>
            {name}
          </span>
        </span>
        {others.length > 0 && <span className="mt-1">{CHEVRON}</span>}
      </button>
      {open && (
        <div
          id={menuId}
          className="absolute top-full right-0 left-0 z-40 mt-1 rounded-md border border-border bg-surface p-1 shadow-overlay"
        >
          <p className="px-2 py-1 text-xs text-muted">Switch workspace</p>
          <ul>
            {visible.map((w) => {
              const isCurrent = w.code === ws;
              return (
                <li key={w.code}>
                  <Link
                    href={switchWorkspaceHref(pathname, ws, w.code)}
                    aria-current={isCurrent ? "true" : undefined}
                    onClick={() => setOpen(false)}
                    className={cx(
                      "block rounded-sm px-2 py-1.5 text-base",
                      isCurrent ? "bg-accent-subtle font-medium text-accent-text" : "text-primary hover:bg-surface-muted",
                    )}
                  >
                    {w.name}
                    {isCurrent && <span className="sr-only"> (current)</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

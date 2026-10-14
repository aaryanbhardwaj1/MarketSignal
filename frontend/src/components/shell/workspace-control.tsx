"use client";

import { BookOpenText, Check, ChevronDown } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useWorkspaces } from "@/lib/api/hooks/core";
import type { Workspace } from "@/lib/api/types";
import { cx } from "@/lib/cx";
import { splitWorkspaceName } from "@/lib/format";
import { evidenceLibraryHref } from "@/lib/routes";
import { Popover } from "../ui/popover";
import { isTestWorkspace, switchWorkspaceHref } from "./nav";

/** Workspaces a person may switch to: never the test-harness codes. */
export function visibleWorkspaces(workspaces: readonly Workspace[] | undefined): Workspace[] {
  return (workspaces ?? []).filter((w) => !isTestWorkspace(w.code));
}

function WorkspaceName({ full }: { full: string }) {
  const { name, detail } = splitWorkspaceName(full);
  return (
    <>
      <span className="block truncate">{name}</span>
      {detail && <span className="block truncate text-xs font-normal text-muted">{detail}</span>}
    </>
  );
}

const ROW = "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm";

/**
 * Quiet top-bar control naming the current workspace. Its popover shows the full name and
 * engagement, a switcher when more than one workspace is visible (keeping the current section),
 * and the link to the Evidence library. Never shows a workspace code.
 */
export function WorkspaceControl({ ws, onNavigate }: { ws: string; onNavigate?: () => void }) {
  const pathname = usePathname() ?? "";
  const workspaces = useWorkspaces();
  const visible = visibleWorkspaces(workspaces.data);
  const current = workspaces.data?.find((w) => w.code === ws);

  if (workspaces.isPending) {
    return (
      <span className="ms-skeleton block h-5 w-28 rounded-md" aria-busy="true">
        <span className="sr-only">Loading workspace</span>
      </span>
    );
  }

  const full = current?.name ?? (workspaces.isError ? "Workspace unavailable" : "Unknown workspace");
  const { name, detail } = splitWorkspaceName(full);

  return (
    <Popover
      label="Workspace"
      trigger={
        <button
          type="button"
          title={current?.name}
          className="flex h-8 max-w-56 min-w-0 items-center gap-1 rounded-md px-2 text-sm font-medium text-secondary transition-colors duration-(--duration-fast) hover:bg-surface-muted hover:text-primary"
        >
          <span className="sr-only">Current workspace: </span>
          <span className="truncate">{name}</span>
          <ChevronDown aria-hidden className="size-3.5 shrink-0 text-muted" />
        </button>
      }
      panelClassName="w-72"
    >
      {(close) => (
        <>
          <div className="px-2.5 pt-2 pb-2.5">
            <p className="text-sm font-semibold text-primary">{name}</p>
            {detail && <p className="mt-0.5 text-xs text-muted">{detail}</p>}
          </div>
          {visible.length > 1 && (
            <div className="border-t border-border py-1">
              <p className="px-2.5 pt-1 pb-1 text-xs text-muted">Switch workspace</p>
              <ul>
                {visible.map((w) => {
                  const isCurrent = w.code === ws;
                  return (
                    <li key={w.code}>
                      <Link
                        href={switchWorkspaceHref(pathname, ws, w.code)}
                        aria-current={isCurrent ? "true" : undefined}
                        onClick={() => {
                          close();
                          onNavigate?.();
                        }}
                        className={cx(ROW, "items-start", isCurrent ? "font-medium text-primary" : "text-secondary hover:bg-surface-muted hover:text-primary")}
                      >
                        <span className="min-w-0 flex-1">
                          <WorkspaceName full={w.name} />
                        </span>
                        {isCurrent && <Check aria-hidden className="mt-0.5 size-3.5 shrink-0 text-accent-text" />}
                        {isCurrent && <span className="sr-only"> (current)</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          <div className="border-t border-border pt-1">
            <Link
              href={evidenceLibraryHref(ws)}
              onClick={() => {
                close();
                onNavigate?.();
              }}
              className={cx(ROW, "text-secondary hover:bg-surface-muted hover:text-primary")}
            >
              <BookOpenText aria-hidden className="size-4 text-muted" />
              Evidence library
            </Link>
          </div>
        </>
      )}
    </Popover>
  );
}

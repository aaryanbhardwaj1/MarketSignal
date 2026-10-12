"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/lib/cx";
import { ModelStatus } from "./model-status";
import { NAV, activeNavId } from "./nav";
import { WorkspaceControl } from "./workspace-control";

/** Product wordmark (no logo art). */
export function Wordmark({ ws }: { ws: string }) {
  return (
    <Link
      href={`/w/${encodeURIComponent(ws)}/overview`}
      className="rounded-sm text-md font-semibold tracking-tight text-primary"
    >
      MarketSignal
    </Link>
  );
}

/** Grouped primary navigation; `aria-current="page"` marks the active section. */
export function SidebarNav({ ws, onNavigate }: { ws: string; onNavigate?: () => void }) {
  const pathname = usePathname() ?? "";
  const active = activeNavId(pathname, ws);
  return (
    <nav aria-label="Primary" className="flex flex-col gap-5">
      {NAV.map((group) => {
        const headingId = `nav-${group.group.toLowerCase().replace(/\s+/g, "-")}`;
        return (
          <div key={group.group}>
            <p id={headingId} className="px-2 pb-1 text-xs font-medium text-muted">
              {group.group}
            </p>
            <ul aria-labelledby={headingId} className="flex flex-col gap-px">
              {group.items.map((entry) => {
                const isActive = entry.id === active;
                return (
                  <li key={entry.id}>
                    <Link
                      href={entry.href(ws)}
                      aria-current={isActive ? "page" : undefined}
                      onClick={onNavigate}
                      className={cx(
                        "flex h-8 items-center rounded-md px-2 text-base",
                        isActive
                          ? "bg-accent-subtle font-medium text-accent-text"
                          : "text-secondary hover:bg-surface-muted hover:text-primary",
                      )}
                    >
                      {entry.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

/** Sidebar body shared by the desktop rail and the mobile menu panel. */
export function Sidebar({ ws, onNavigate, showWordmark = true }: { ws: string; onNavigate?: () => void; showWordmark?: boolean }) {
  return (
    <div className="flex h-full flex-col gap-5 px-3 py-4">
      {showWordmark && (
        <div className="px-2">
          <Wordmark ws={ws} />
        </div>
      )}
      <WorkspaceControl ws={ws} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <SidebarNav ws={ws} onNavigate={onNavigate} />
      </div>
      <div className="border-t border-border px-2 pt-3">
        <ModelStatus />
      </div>
    </div>
  );
}

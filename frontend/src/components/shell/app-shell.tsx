"use client";

import { X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import { BrandLockup } from "../brand/brand-mark";
import { PageTransition } from "../motion/page-transition";
import { IconButton } from "../ui/icon-button";
import { ConversationSidebar } from "./conversation-sidebar";
import { NewChatSignalProvider } from "./new-chat-signal";
import { PrimaryNav } from "./primary-nav";
import { useSidebarCollapsed } from "./sidebar-state";
import { TopBar } from "./top-bar";
import { WorkspaceControl } from "./workspace-control";

export const MAIN_CONTENT_ID = "main-content";

/** Matches the `lg` breakpoint, where the sidebar is docked rather than a sheet. */
const DOCKED_QUERY = "(min-width: 64rem)";

/** True for the sidebar toggle chord: Cmd+\ on Apple platforms, Ctrl+\ elsewhere. */
export function isSidebarShortcut(event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "shiftKey">): boolean {
  return event.key === "\\" && (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey;
}

const FOCUSABLE = "a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])";

/** Keeps Tab and Shift+Tab inside `container`. */
function trapTab(event: ReactKeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") return;
  const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => !el.closest("[hidden],[inert]"));
  if (items.length === 0) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

/** Small-screen overlay: workspace, sections and conversations; Escape, backdrop or navigation close it. */
function SidebarSheet({ ws, id, now, onClose }: { ws: string; id: string; now: Date; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
  }, []);
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button type="button" aria-label="Close menu" tabIndex={-1} onClick={onClose} className="ms-fade-in absolute inset-0 bg-ink/30" />
      <div
        ref={panel}
        id={id}
        role="dialog"
        aria-modal="true"
        aria-label="Conversations and navigation"
        onKeyDown={trapTab}
        className="ms-sheet-in absolute inset-y-0 left-0 flex w-[min(20rem,88vw)] flex-col border-r border-border bg-surface shadow-overlay"
      >
        <div className="flex h-(--height-topbar) shrink-0 items-center justify-between gap-2 border-b border-border px-3">
          <BrandLockup size={20} />
          <IconButton label="Close menu" icon={<X />} onClick={onClose} tooltip={false} />
        </div>
        <div className="flex flex-col gap-2 border-b border-border px-2 py-2 md:hidden">
          <div className="sm:hidden">
            <WorkspaceControl ws={ws} onNavigate={onClose} />
          </div>
          <PrimaryNav ws={ws} orientation="vertical" onNavigate={onClose} />
        </div>
        <div className="min-h-0 flex-1">
          <ConversationSidebar ws={ws} variant="sheet" now={now} onNavigate={onClose} />
        </div>
      </div>
    </div>
  );
}

/**
 * Workspace chrome: skip link, top bar, the conversation sidebar (docked and collapsible from
 * `lg`, an overlay sheet below), and the main column with the page-enter transition.
 */
export function AppShell({ ws, children }: { ws: string; children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [routePath, setRoutePath] = useState(pathname);
  const [now, setNow] = useState(() => new Date());
  const sheetId = useId();
  const menuButton = useRef<HTMLButtonElement>(null);

  // Route change: close the sheet and refresh the recency reference (state derived during render).
  if (routePath !== pathname) {
    setRoutePath(pathname);
    setNow(new Date());
    if (sheetOpen) setSheetOpen(false);
  }

  const closeSheet = () => {
    setSheetOpen(false);
    menuButton.current?.focus();
  };

  const latest = useRef({ collapsed, sheetOpen, setCollapsed });
  useEffect(() => {
    latest.current = { collapsed, sheetOpen, setCollapsed };
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const state = latest.current;
      if (event.key === "Escape" && state.sheetOpen) {
        setSheetOpen(false);
        menuButton.current?.focus();
        return;
      }
      if (!isSidebarShortcut(event)) return;
      event.preventDefault();
      if (window.matchMedia(DOCKED_QUERY).matches) state.setCollapsed(!state.collapsed);
      else setSheetOpen((open) => !open);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <NewChatSignalProvider>
      <div className="flex min-h-dvh flex-col">
        <a
          href={`#${MAIN_CONTENT_ID}`}
          className="sr-only z-[60] rounded-md bg-surface px-3 py-2 text-base font-medium text-primary shadow-overlay focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
        >
          Skip to main content
        </a>

        <TopBar ws={ws} menuOpen={sheetOpen} onMenu={() => setSheetOpen((v) => !v)} menuButtonRef={menuButton} menuId={sheetId} />

        <div className="flex flex-1">
          <aside
            aria-label="Conversation history"
            data-collapsed={collapsed}
            className={cx(
              "sticky top-(--height-topbar) hidden h-[calc(100dvh-var(--height-topbar))] shrink-0 overflow-hidden border-r border-border bg-surface lg:block",
              "transition-[width] duration-(--duration-base) ease-standard motion-reduce:transition-none",
              collapsed ? "w-(--width-rail)" : "w-(--width-sidebar)",
            )}
          >
            <ConversationSidebar ws={ws} collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} now={now} />
          </aside>

          <main id={MAIN_CONTENT_ID} tabIndex={-1} className="min-w-0 flex-1 focus:outline-none">
            <PageTransition>{children}</PageTransition>
          </main>
        </div>

        {sheetOpen && <SidebarSheet ws={ws} id={sheetId} now={now} onClose={closeSheet} />}
      </div>
    </NewChatSignalProvider>
  );
}

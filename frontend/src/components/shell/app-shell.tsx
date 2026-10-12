"use client";

import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Sidebar, Wordmark } from "./sidebar";

export const MAIN_CONTENT_ID = "main-content";

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.75">
      {open ? <path d="m4 4 8 8M12 4l-8 8" strokeLinecap="round" /> : <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" strokeLinecap="round" />}
    </svg>
  );
}

/**
 * Workspace chrome: skip link, a persistent 15rem sidebar at 1024px and up, and below that a
 * top bar whose menu button reveals the same navigation.
 */
export function AppShell({ ws, children }: { ws: string; children: ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(pathname);
  const menuId = useId();
  const menuButton = useRef<HTMLButtonElement>(null);

  // Close the mobile menu whenever the route changes (state derived during render).
  if (menuPath !== pathname) {
    setMenuPath(pathname);
    if (menuOpen) setMenuOpen(false);
  }

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <a
        href={`#${MAIN_CONTENT_ID}`}
        className="sr-only z-50 rounded-md bg-surface px-3 py-2 text-base font-medium text-primary shadow-overlay focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to main content
      </a>

      <aside
        aria-label="Workspace navigation"
        className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-border bg-surface lg:block"
      >
        <Sidebar ws={ws} />
      </aside>

      <header className="sticky top-0 z-30 border-b border-border bg-surface lg:hidden">
        <div className="flex h-12 items-center justify-between gap-3 px-4">
          <Wordmark ws={ws} />
          <button
            ref={menuButton}
            type="button"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => setMenuOpen((v) => !v)}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong bg-surface px-2.5 text-sm font-medium text-primary hover:bg-surface-muted"
          >
            <MenuIcon open={menuOpen} />
            Menu
          </button>
        </div>
        {menuOpen && (
          <div id={menuId} className="max-h-[calc(100dvh-3rem)] overflow-y-auto border-t border-border">
            <Sidebar ws={ws} showWordmark={false} onNavigate={() => setMenuOpen(false)} />
          </div>
        )}
      </header>

      <main id={MAIN_CONTENT_ID} tabIndex={-1} className="min-w-0 flex-1 focus:outline-none">
        {children}
      </main>
    </div>
  );
}

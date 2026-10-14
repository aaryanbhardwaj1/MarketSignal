"use client";

import { useCallback, useEffect, useState } from "react";

export const SIDEBAR_STORAGE_KEY = "marketsignal.sidebar.collapsed";

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null; // storage disabled (privacy mode, sandboxed iframe)
  }
}

/** Persisted collapse state; false when nothing is stored or storage is unavailable. */
export function readSidebarCollapsed(storage: StorageLike | null = defaultStorage()): boolean {
  try {
    return storage?.getItem(SIDEBAR_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Stores the collapse state; failures (quota, disabled storage) are ignored. */
export function writeSidebarCollapsed(collapsed: boolean, storage: StorageLike | null = defaultStorage()): void {
  try {
    storage?.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    // Not persisting is acceptable: the toggle still works for this page view.
  }
}

/**
 * Collapse state for the docked sidebar. Starts expanded on the server and the first client
 * render (no hydration mismatch), then adopts the stored value after mount.
 */
export function useSidebarCollapsed(): readonly [boolean, (next: boolean) => void] {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    // Reading storage must wait for mount; this is the one-time sync from an external store.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (readSidebarCollapsed()) setCollapsed(true);
  }, []);

  const set = useCallback((next: boolean) => {
    setCollapsed(next);
    writeSidebarCollapsed(next);
  }, []);

  return [collapsed, set] as const;
}

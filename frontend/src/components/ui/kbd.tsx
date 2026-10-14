"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { cx } from "@/lib/cx";

/** A keyboard key or chord, e.g. `<Kbd>⌘\</Kbd>`. Quiet on light surfaces, legible on ink tooltips. */
export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cx(
        "inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-sm border border-current/25 px-1 font-sans text-2xs font-medium tabular-nums opacity-80",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

const subscribeNever = () => () => {};

function detectApple(): boolean {
  const platform = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform ?? navigator.platform;
  return /mac|iphone|ipad|ipod/i.test(platform ?? "");
}

/** True on Apple platforms (⌘ shortcuts). False on the server and the first render, so hydration matches. */
export function useIsApple(): boolean {
  return useSyncExternalStore(subscribeNever, detectApple, () => false);
}

/** "⌘\" on Apple platforms, "Ctrl+\" elsewhere, for a Mod+`key` shortcut. */
export function useModShortcut(key: string): string {
  return useIsApple() ? `⌘${key}` : `Ctrl+${key}`;
}

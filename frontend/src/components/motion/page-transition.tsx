"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";
import { cx } from "@/lib/cx";

/**
 * The part of a pathname that counts as "a different page" for the enter animation: the
 * section under `/w/{ws}/` (two segments for `dev/...`). Moving between conversations or
 * records inside one section does not re-animate, so a new chat getting its URL never flickers.
 */
export function transitionKey(pathname: string): string {
  const parts = pathname.split("?")[0].split("/").filter(Boolean);
  if (parts[0] !== "w") return parts.slice(0, 1).join("/");
  const rest = parts.slice(2);
  const depth = rest[0] === "dev" ? 2 : 1;
  return [parts[1], ...rest.slice(0, depth)].join("/");
}

/**
 * Subtle route-change motion (fade + 4px rise, 200ms). CSS-only: the enter class is restarted
 * when the section changes; children are never remounted, so page state survives. Reduced motion
 * falls back to a fade (see styles/motion.css).
 */
export function PageTransition({ children, className }: { children: ReactNode; className?: string }) {
  const pathname = usePathname() ?? "";
  const key = transitionKey(pathname);
  const ref = useRef<HTMLDivElement>(null);
  const previous = useRef(key);

  useEffect(() => {
    const el = ref.current;
    if (!el || previous.current === key) return;
    previous.current = key;
    el.classList.remove("ms-page-enter");
    void el.offsetWidth; // restart the CSS animation
    el.classList.add("ms-page-enter");
  }, [key]);

  return (
    <div ref={ref} className={cx("ms-page-enter", className)}>
      {children}
    </div>
  );
}

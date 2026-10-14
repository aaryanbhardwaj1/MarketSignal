"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLayoutEffect, useRef, useState } from "react";
import { cx } from "@/lib/cx";
import { PRIMARY_NAV, activeNavId } from "./nav";

interface Indicator {
  left: number;
  width: number;
  /** False for the first placement, so the underline does not slide in from the left edge. */
  animate: boolean;
}

/**
 * Chat · Insights · Growth Opportunities · Analytics. The active item is set in ink at medium
 * weight with an accent underline that slides between items (`aria-current="page"`).
 * `orientation="vertical"` is the stacked form used in the small-screen sheet.
 */
export function PrimaryNav({
  ws,
  orientation = "horizontal",
  onNavigate,
  className,
}: {
  ws: string;
  orientation?: "horizontal" | "vertical";
  onNavigate?: () => void;
  className?: string;
}) {
  const pathname = usePathname() ?? "";
  const active = activeNavId(pathname, ws);
  const listRef = useRef<HTMLUListElement>(null);
  const [indicator, setIndicator] = useState<Indicator | null>(null);
  const horizontal = orientation === "horizontal";

  useLayoutEffect(() => {
    if (!horizontal) return;
    const list = listRef.current;
    if (!list) return;
    const place = () => {
      const link = list.querySelector<HTMLElement>("a[aria-current='page']");
      setIndicator((prev) =>
        link && link.offsetWidth > 0 ? { left: link.offsetLeft, width: link.offsetWidth, animate: prev !== null } : null,
      );
    };
    place();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(place);
    observer.observe(list);
    return () => observer.disconnect();
  }, [active, horizontal]);

  return (
    <nav aria-label="Primary" className={className}>
      <ul ref={listRef} className={cx("relative flex", horizontal ? "h-(--height-topbar) items-stretch gap-1" : "flex-col gap-px")}>
        {PRIMARY_NAV.map((entry) => {
          const isActive = entry.id === active;
          return (
            <li key={entry.id} className="flex">
              <Link
                href={entry.href(ws)}
                aria-current={isActive ? "page" : undefined}
                onClick={onNavigate}
                className={cx(
                  "flex items-center rounded-md text-sm whitespace-nowrap transition-colors duration-(--duration-fast) ease-standard focus-visible:outline-offset-[-2px]",
                  horizontal ? "px-2.5" : "h-9 w-full px-3",
                  isActive
                    ? cx("font-medium text-primary", !horizontal && "bg-accent-subtle text-accent-text")
                    : "text-secondary hover:text-primary",
                  !horizontal && !isActive && "hover:bg-surface-muted",
                )}
              >
                {entry.label}
              </Link>
            </li>
          );
        })}
        {horizontal && indicator && (
          <li
            aria-hidden
            className={cx(
              "pointer-events-none absolute bottom-0 left-0 h-0.5 rounded-full bg-accent",
              indicator.animate && "transition-[transform,width] duration-(--duration-base) ease-standard motion-reduce:transition-none",
            )}
            style={{ width: indicator.width, transform: `translateX(${indicator.left}px)` }}
          />
        )}
      </ul>
    </nav>
  );
}

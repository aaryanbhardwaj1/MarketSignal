"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Measures an element's width with ResizeObserver. Starts at `fallback` on the server and the
 * first client render (no hydration mismatch), then follows the real width.
 */
export function useChartWidth<T extends HTMLElement = HTMLDivElement>(fallback = 560) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.floor(entry.contentRect.width);
      if (next > 0) setWidth(next);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

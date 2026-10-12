"use client";

import { useEffect } from "react";

const SUFFIX = " · MarketSignal";

/**
 * Sets the tab title to a record's name once it loads ("Knit Runner fit · Growth Opportunities"),
 * so detail pages are distinguishable and Next's route announcer reads the change. Static
 * `metadata` on the route supplies the section title until then.
 */
export function useDocumentTitle(name: string | null | undefined, section: string): void {
  useEffect(() => {
    if (!name) return;
    const previous = document.title;
    document.title = `${name} · ${section}${SUFFIX}`;
    return () => {
      document.title = previous;
    };
  }, [name, section]);
}

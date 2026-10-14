"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { Disclosure } from "../ui/disclosure";

function subscribeHash(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** True on the client when the URL fragment targets `id` (e.g. a link to `#datasets`). */
export function useHashTarget(id: string): boolean {
  return useSyncExternalStore(
    subscribeHash,
    () => window.location.hash === `#${id}`,
    () => false,
  );
}

/**
 * A quiet, collapsed section below the main content of a page. It opens by itself when the URL
 * fragment points at it, so existing `#saved-results` / `#datasets` links still land on content.
 */
export function SecondarySection({
  id,
  title,
  description,
  defaultOpen = false,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const targeted = useHashTarget(id);
  const open = defaultOpen || targeted;
  return (
    <section id={id} aria-label={title} className="scroll-mt-20">
      <Disclosure key={open ? "open" : "closed"} defaultOpen={open} summary={<span className="text-base font-semibold">{title}</span>}>
        <div className="flex flex-col gap-3">
          {description && <p className="text-sm text-muted">{description}</p>}
          {children}
        </div>
      </Disclosure>
    </section>
  );
}

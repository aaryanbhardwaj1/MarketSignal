"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { useAskSession } from "./ask-session";

/** Longest question accepted from a `?q=` link (other pages: "Investigate in Chat", "Ask a follow-up"). */
export const PREFILL_MAX_CHARS = 2000;

/** Question to prefill from the raw `q` value: trimmed, capped at 2000 chars; null when empty. */
export function prefillQuestion(raw: string | null | undefined): string | null {
  if (typeof raw !== "string") return null;
  const text = raw.trim();
  return text ? text.slice(0, PREFILL_MAX_CHARS).trimEnd() : null;
}

/** Current search params without `q`, as "?a=b" or "". */
export function withoutQuery(params: URLSearchParams): string {
  const next = new URLSearchParams(params);
  next.delete("q");
  const s = next.toString();
  return s ? `?${s}` : "";
}

/**
 * On the Chat start page, `?q=<question>` prefills (and focuses) the composer without sending it,
 * then removes `q` from the URL so a refresh does not prefill again. Renders nothing.
 */
export function AskPrefillFromQuery() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { fillComposer } = useAskSession();
  const handled = useRef<string | null>(null);
  const raw = params?.get("q") ?? null;

  useEffect(() => {
    if (raw === null || handled.current === raw || !params) return;
    handled.current = raw;
    const question = prefillQuestion(raw);
    if (question) fillComposer(question);
    router.replace(`${pathname}${withoutQuery(new URLSearchParams(params.toString()))}`, { scroll: false });
  }, [raw, params, pathname, router, fillComposer]);

  return null;
}

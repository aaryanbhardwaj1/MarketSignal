"use client";

import { ArrowRight, BookmarkCheck } from "lucide-react";
import Link from "next/link";
import { BrandMark } from "@/components/brand/brand-mark";
import { Skeleton } from "@/components/ui/states";
import type { ConversationSummary } from "@/lib/api/contracts";
import { useConversations } from "@/lib/api/hooks/core";
import { modeLabel } from "@/lib/run-mode";
import { askHref } from "@/lib/routes";
import { useAskSession } from "./ask-session";
import { Composer } from "./composer";
import { SAVED_RESEARCH_ANCHOR, useHydrated } from "./model-unavailable";

/** Example strategy questions; selecting one fills the composer (it is not sent). */
export const EXAMPLE_QUESTIONS = [
  "Where are the strongest growth opportunities among younger customers?",
  "What customer pain points are suppressing conversion?",
  "What evidence contradicts our current growth hypothesis?",
  "Which competitor signals should we be paying attention to?",
  "What are the largest blockers to customer satisfaction?",
] as const;
export const SAVED_RESEARCH_LIMIT = 3;

/** Featured conversations, one per question (the same question may be saved in two modes). */
export function savedResearch(rows: readonly ConversationSummary[], limit = SAVED_RESEARCH_LIMIT): ConversationSummary[] {
  return rows.filter((row, i) => rows.findIndex((r) => r.title === row.title) === i).slice(0, limit);
}

function Examples() {
  const { fillComposer } = useAskSession();
  return (
    <section aria-labelledby="examples-heading" className="mt-10">
      <h2 id="examples-heading" className="text-sm font-medium text-muted">
        Example questions
      </h2>
      <p id="examples-hint" className="sr-only">
        Selecting a question adds it to the question box without sending it.
      </p>
      <ul className="mt-2 flex flex-col divide-y divide-border border-y border-border">
        {EXAMPLE_QUESTIONS.map((q) => (
          <li key={q}>
            <button
              type="button"
              aria-describedby="examples-hint"
              onClick={() => fillComposer(q)}
              className="group flex w-full items-center justify-between gap-4 px-1 py-2.5 text-left text-base text-secondary transition-colors duration-(--duration-fast) ease-standard hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            >
              <span className="min-w-0">{q}</span>
              <ArrowRight
                aria-hidden
                className="size-4 shrink-0 text-muted transition-transform duration-(--duration-fast) ease-standard group-hover:text-accent-text motion-safe:group-hover:translate-x-0.5"
              />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SavedResearch({ ws }: { ws: string }) {
  const featured = useConversations(ws, { featured: true });
  // The sidebar may already have these cached: wait for hydration so the first client render
  // matches the server's skeleton.
  const hydrated = useHydrated();
  const pending = !hydrated || featured.isPending;
  const rows = hydrated ? (featured.data?.pages.flatMap((p) => p.items) ?? []) : [];
  const saved = savedResearch(rows);
  const answers = (title: string) => rows.filter((r) => r.title === title).length;
  if (!pending && saved.length === 0) return null;

  return (
    <section id={SAVED_RESEARCH_ANCHOR} aria-labelledby="saved-research-heading" className="mt-10 scroll-mt-24">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="saved-research-heading" className="text-sm font-medium text-muted">
          Saved research
        </h2>
        <p className="text-xs text-muted">Verified answers with cited evidence. Open one to inspect it.</p>
      </div>
      <ul className="mt-2 grid gap-2 sm:grid-cols-3">
        {pending
          ? Array.from({ length: SAVED_RESEARCH_LIMIT }, (_, i) => (
              <li key={i}>
                <Skeleton height="4.5rem" />
              </li>
            ))
          : saved.map((row) => (
              <li key={row.conversation_id} className="min-w-0">
                <Link
                  href={askHref(ws, row.conversation_id)}
                  className="flex h-full flex-col gap-2 rounded-lg border border-border bg-surface px-3 py-2.5 transition-[border-color,box-shadow] duration-(--duration-fast) ease-standard hover:border-border-strong hover:shadow-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                >
                  <span className="line-clamp-2 text-sm font-medium leading-snug text-primary">{row.title}</span>
                  <span className="mt-auto flex items-center gap-1.5 text-xs text-muted">
                    <BookmarkCheck aria-hidden className="size-3.5 shrink-0 text-accent-text" />
                    {answers(row.title) > 1
                      ? `${modeLabel("research")} and ${modeLabel("standard")} answers`
                      : row.last_run
                        ? `${modeLabel(row.last_run.mode)} answer`
                        : "Saved answer"}
                  </span>
                </Link>
              </li>
            ))}
      </ul>
    </section>
  );
}

/** Chat start page: what MarketSignal does, example questions, saved research and the composer. */
export function AskIntro({ ws }: { ws: string }) {
  return (
    <div className="flex min-h-[calc(100dvh-var(--height-topbar)-4rem)] flex-col">
      <div className="ms-page-enter flex flex-1 flex-col justify-center pb-10 pt-6 md:pt-12">
        <BrandMark size={28} />
        <h1 className="mt-5 text-display font-semibold text-primary">What do you want to investigate?</h1>
        <p className="mt-2 max-w-prose text-md text-secondary">
          MarketSignal answers strategy questions from your workspace evidence, citing the passages it relies on and
          computing figures with a deterministic analytics engine.
        </p>
        <Examples />
        <SavedResearch ws={ws} />
      </div>
      <section aria-label="Ask a question" className="sticky bottom-0 -mx-1 bg-canvas px-1 pb-4 pt-2">
        <Composer conversationId={null} />
      </section>
    </div>
  );
}

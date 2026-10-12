"use client";

import Link from "next/link";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/states";
import { useConversations } from "@/lib/api/hooks/core";
import { modeLabel } from "@/lib/run-mode";
import { askHref } from "@/lib/routes";
import { useAskSession } from "./ask-session";
import { Composer } from "./composer";

/** Generic examples, used only when the workspace has no featured conversations to open. */
const FALLBACK_EXAMPLES = [
  "What are the most common reasons customers give for abandoning an order?",
  "Where do competitors' offers differ most from ours, according to the evidence?",
  "Which customer segments show the strongest demand signals, and what is the evidence?",
  "What do internal documents say about our plans that customers have not yet seen?",
];
const EXAMPLE_COUNT = 4;

const ITEM =
  "flex w-full items-start gap-3 rounded-md border border-border bg-surface px-3 py-2.5 text-left text-base text-primary hover:border-border-strong hover:bg-surface-muted";

function Arrow() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="mt-1 h-3.5 w-3.5 shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M3 8h10M9 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** No conversation selected: what Ask does, example questions and the composer. */
export function AskIntro({ ws }: { ws: string }) {
  const { fillComposer } = useAskSession();
  const featured = useConversations(ws, { featured: true });
  const rows = featured.data?.pages.flatMap((p) => p.items) ?? [];
  // Featured lists can hold the same question asked in two modes; show each question once and
  // say that a second answer exists for comparison.
  const saved = rows.filter((row, i) => rows.findIndex((r) => r.title === row.title) === i).slice(0, EXAMPLE_COUNT);
  const answers = (title: string) => rows.filter((r) => r.title === title).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Ask MarketSignal"
        description="Ask questions across customer, competitor, market and internal evidence. Answers cite the passages they rely on, separate computed figures from quoted evidence, and name what the evidence does not cover."
      />
      <section aria-labelledby="examples-heading">
        <h2 id="examples-heading" className="text-md font-semibold text-primary">
          Example questions
        </h2>
        <p className="mt-0.5 text-sm text-muted">
          {saved.length > 0 ? "Open a saved answer to see how MarketSignal cites its evidence." : "Select a question to add it to the composer."}
        </p>
        <ul className="mt-3 flex flex-col gap-2">
          {featured.isPending
            ? Array.from({ length: EXAMPLE_COUNT }, (_, i) => (
                <li key={i}>
                  <Skeleton height="2.75rem" />
                </li>
              ))
            : saved.length > 0
              ? saved.map((row) => (
                  <li key={row.conversation_id}>
                    <Link href={askHref(ws, row.conversation_id)} className={ITEM}>
                      <Arrow />
                      <span className="min-w-0">
                        {row.title}
                        {answers(row.title) > 1 && (
                          <span className="mt-0.5 block text-sm text-muted">
                            Two saved answers to compare: {modeLabel("research")} and {modeLabel("standard")}
                          </span>
                        )}
                      </span>
                    </Link>
                  </li>
                ))
              : FALLBACK_EXAMPLES.map((q) => (
                  <li key={q}>
                    <button type="button" className={ITEM} onClick={() => fillComposer(q)}>
                      <Arrow />
                      <span className="min-w-0">{q}</span>
                    </button>
                  </li>
                ))}
        </ul>
      </section>
      <section aria-label="Ask a question">
        <Composer conversationId={null} />
      </section>
    </div>
  );
}

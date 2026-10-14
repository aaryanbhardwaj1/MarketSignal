"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import { Disclosure } from "@/components/ui/disclosure";
import type { Deck, DeckNote } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { DeckSlideFrame, DeckSlideThumb } from "./deck-slide";
import type { ExclusionView } from "./deck-view";

const STEP: Record<string, number> = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1, PageUp: -1, PageDown: 1 };

/** Next slide position for a key, or null when the key is not a navigation key. Pure. */
export function slideForKey(key: string, current: number, total: number): number | null {
  if (total === 0) return null;
  if (key === "Home") return 0;
  if (key === "End") return total - 1;
  const step = STEP[key];
  return step === undefined ? null : Math.min(total - 1, Math.max(0, current + step));
}

/** "Not included: <title> — <reason>" so nothing silently disappears from the deck. */
export function ExcludedList({ items }: { items: readonly ExclusionView[] }) {
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="deck-excluded" className="rounded-lg border border-border bg-sunken px-4 py-3">
      <h3 id="deck-excluded" className="text-sm font-semibold text-primary">
        {items.length === 1 ? "1 finding was left out" : `${items.length} findings were left out`}
      </h3>
      <ul className="mt-1.5 flex flex-col gap-1 text-sm text-secondary">
        {items.map((e) => (
          <li key={e.id}>
            Not included: <span className="font-medium text-primary">{e.title}</span> — {e.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}

function SpeakerNotes({ notes }: { notes: readonly DeckNote[] }) {
  return (
    <Disclosure variant="plain" summary={`Speaker notes (${notes.length} ${notes.length === 1 ? "source" : "sources"})`}>
      {notes.length === 0 ? (
        <p className="mt-2 text-sm text-muted">This slide cites no sources.</p>
      ) : (
        <ol className="mt-2 flex flex-col gap-2">
          {notes.map((n) => (
            <li key={n.n} className="flex gap-3 text-sm">
              <span className="w-6 shrink-0 text-right tabular-nums text-accent-text">[{n.n}]</span>
              <span className="min-w-0">
                <span className="font-medium text-primary">{n.source_title}</span>
                <span className="text-muted"> · {n.locator}</span>
                {n.quote && <span className="mt-0.5 block italic text-secondary">&ldquo;{n.quote}&rdquo;</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Disclosure>
  );
}

/** Slide-by-slide preview: thumbnail rail + the current slide, arrow keys to move. */
export function DeckPreview({ deck, initial = 0 }: { deck: Deck; initial?: number }) {
  const total = deck.slides.length;
  const [current, setCurrent] = useState(Math.min(initial, Math.max(0, total - 1)));
  const slide = deck.slides[current];
  if (!slide) return null;

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const next = slideForKey(event.key, current, total);
    if (next === null) return;
    event.preventDefault();
    setCurrent(next);
  };

  return (
    <section aria-label="Presentation preview" className="grid gap-5 lg:grid-cols-[10rem_minmax(0,1fr)]">
      <ol aria-label="Slides" className="flex gap-2 overflow-x-auto pb-1 lg:max-h-[70vh] lg:flex-col lg:overflow-y-auto lg:overflow-x-visible lg:pb-0 lg:pr-1">
        {deck.slides.map((s, i) => (
          <li key={s.index} className="w-36 shrink-0 lg:w-full">
            <button
              type="button"
              onClick={() => setCurrent(i)}
              onKeyDown={onKeyDown}
              aria-current={i === current ? "true" : undefined}
              aria-label={`Slide ${s.index}: ${s.title}`}
              className={cx(
                "flex w-full items-start gap-2 rounded-md p-1 text-left transition-colors duration-(--duration-fast) ease-standard",
                i === current ? "bg-accent-subtle ring-1 ring-accent" : "hover:bg-sunken",
              )}
            >
              <span className="w-4 shrink-0 pt-0.5 text-right text-2xs tabular-nums text-muted">{s.index}</span>
              <DeckSlideThumb slide={s} />
            </button>
          </li>
        ))}
      </ol>
      <div className="flex min-w-0 flex-col gap-3">
        <div tabIndex={0} onKeyDown={onKeyDown} aria-roledescription="slide viewer" aria-live="polite" className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
          <DeckSlideFrame slide={slide} total={total} footer={deck.title} />
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted">Use the arrow keys to move between slides.</p>
          <div className="flex shrink-0 items-center gap-1 text-sm text-muted">
            <button
              type="button"
              onClick={() => setCurrent(Math.max(0, current - 1))}
              disabled={current === 0}
              aria-label="Previous slide"
              className="rounded-md p-1.5 hover:bg-sunken hover:text-primary disabled:opacity-40"
            >
              <ChevronLeft aria-hidden size={16} />
            </button>
            <span className="tabular-nums">
              {current + 1} / {total}
            </span>
            <button
              type="button"
              onClick={() => setCurrent(Math.min(total - 1, current + 1))}
              disabled={current === total - 1}
              aria-label="Next slide"
              className="rounded-md p-1.5 hover:bg-sunken hover:text-primary disabled:opacity-40"
            >
              <ChevronRight aria-hidden size={16} />
            </button>
          </div>
        </div>
        <SpeakerNotes key={slide.index} notes={slide.notes} />
      </div>
    </section>
  );
}

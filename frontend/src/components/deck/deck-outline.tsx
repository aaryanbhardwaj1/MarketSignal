import type { Deck } from "@/lib/api/contracts";
import { deckOutline, slidesLabel } from "./deck-view";

function slideRange(slides: readonly number[]): string {
  const first = slides[0];
  const last = slides[slides.length - 1];
  return slides.length === 1 ? `Slide ${first}` : `Slides ${first}–${last}`;
}

/** The structure of the deck the server will produce, read from its preview (never guessed). */
export function DeckOutline({ deck }: { deck: Pick<Deck, "slides" | "counts"> }) {
  const sections = deckOutline(deck);
  const { items, sources } = deck.counts;
  return (
    <div>
      <p className="text-sm tabular-nums text-secondary">
        {slidesLabel(deck.slides.length)} · {items} {items === 1 ? "finding" : "findings"} · {sources}{" "}
        {sources === 1 ? "source" : "sources"}
      </p>
      <ol className="mt-3 flex flex-col">
        {sections.map((s, i) => (
          <li key={`${s.kind}-${i}`} className="flex gap-3 border-l border-border py-1.5 pl-3">
            <div className="min-w-0 flex-1">
              <p className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-medium text-primary">{s.label}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted">{slideRange(s.slides)}</span>
              </p>
              {s.titles.length > 0 && (
                <ul className="mt-0.5 flex flex-col gap-0.5">
                  {s.titles.map((t) => (
                    <li key={t} className="truncate text-xs text-secondary" title={t}>
                      {t}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { DeckPreviewResponse } from "@/lib/api/contracts";
import fixture from "./__fixtures__/deck-preview.json";
import { EMPTY_SELECTION, EmptySelection } from "./deck-builder";
import { DeckOutline } from "./deck-outline";
import { DeckPreview, ExcludedList, slideForKey } from "./deck-preview";
import { DeckSlideFrame } from "./deck-slide";

const DECK = (fixture as DeckPreviewResponse).deck;
const slide = (index: number) => DECK.slides[index - 1];
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("DeckOutline", () => {
  it("lists the server's sections with slide ranges and counts", () => {
    const out = text(renderToStaticMarkup(<DeckOutline deck={DECK} />));
    expect(out).toContain("8 slides · 3 findings · 3 sources");
    expect(out).toContain("Quantitative evidence Slides 4–5");
    expect(out).toContain("Willingness to pay by segment");
    expect(out).toContain("Sources Slide 8");
  });
});

describe("ExcludedList", () => {
  it("names every excluded finding and why", () => {
    const out = text(renderToStaticMarkup(<ExcludedList items={[{ id: "x", title: "Loyalty lapse", reason: "Its main claim no longer has verified support." }]} />));
    expect(out).toContain("1 finding was left out");
    expect(out).toContain("Not included: Loyalty lapse — Its main claim no longer has verified support.");
  });

  it("renders nothing when nothing was excluded", () => {
    expect(renderToStaticMarkup(<ExcludedList items={[]} />)).toBe("");
  });
});

describe("DeckSlideFrame", () => {
  it("renders the title slide with question and meta", () => {
    const out = text(renderToStaticMarkup(<DeckSlideFrame slide={slide(1)} total={8} />));
    expect(out).toContain("Should Northstar launch personalization");
    expect(out).toContain("Northstar · 14 October 2026 · Built from 3 verified findings");
  });

  it("labels interpretive claims and numbers citations", () => {
    const html = renderToStaticMarkup(<DeckSlideFrame slide={slide(6)} total={8} />);
    expect(html).toContain('data-claim="hypothesis"');
    expect(text(html)).toContain("[1] , [2]");
    expect(text(html)).toContain("Evidence: 2 supporting and 0 contradicting passages");
  });

  it("renders statuses, metrics, a bar chart and a truncated table from the JSON", () => {
    expect(renderToStaticMarkup(<DeckSlideFrame slide={slide(2)} total={8} />)).toContain('data-status="strong_evidence"');
    expect(text(renderToStaticMarkup(<DeckSlideFrame slide={slide(4)} total={8} />))).toContain("38%");
    const quant = text(renderToStaticMarkup(<DeckSlideFrame slide={slide(5)} total={8} />));
    expect(quant).toContain("Share willing to pay more");
    expect(quant).toContain("Gen Z 38%");
    expect(quant).toContain("First 2 rows of 3");
  });

  it("renders the sources appendix with quotes", () => {
    const out = text(renderToStaticMarkup(<DeckSlideFrame slide={slide(8)} total={8} />));
    expect(out).toContain("[3] Survey: willingness to pay · Analysis wtp_by_segment");
    expect(out).toContain("“I would pay a little more if it felt made for me.”");
  });
});

describe("DeckPreview", () => {
  it("shows a thumbnail per slide, the current slide and its speaker notes toggle", () => {
    const html = renderToStaticMarkup(<DeckPreview deck={DECK} initial={1} />);
    expect(html.match(/aria-label="Slide \d+: /g)).toHaveLength(8);
    expect(html).toContain('aria-label="Slide 2 of 8: Executive summary"');
    expect(text(html)).toContain("Speaker notes (1 source)");
    expect(html).not.toContain("NORTHSTAR:interviews#p4");
  });

  it("moves with arrow keys within bounds", () => {
    expect(slideForKey("ArrowRight", 0, 8)).toBe(1);
    expect(slideForKey("ArrowLeft", 0, 8)).toBe(0);
    expect(slideForKey("ArrowDown", 7, 8)).toBe(7);
    expect(slideForKey("End", 2, 8)).toBe(7);
    expect(slideForKey("Home", 5, 8)).toBe(0);
    expect(slideForKey("a", 2, 8)).toBeNull();
  });
});

describe("EmptySelection", () => {
  it("teaches where findings come from, with links", () => {
    const html = renderToStaticMarkup(<EmptySelection ws="NORTHSTAR" />);
    expect(text(html)).toContain(EMPTY_SELECTION);
    for (const href of ["/w/NORTHSTAR/insights", "/w/NORTHSTAR/opportunities", "/w/NORTHSTAR/analytics"]) {
      expect(html).toContain(`href="${href}"`);
    }
  });
});

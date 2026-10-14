import { describe, expect, it } from "vitest";
import type { Analysis, DeckPreviewResponse, InsightsBrief } from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import { parseDeckSelection } from "@/lib/views/insights";
import fixture from "./__fixtures__/deck-preview.json";
import {
  canAdd,
  deckErrorMessage,
  deckOutline,
  deckRequest,
  EMPTY_PICK,
  exclusionViews,
  knownIds,
  pickerGroups,
  pickHref,
  pickSize,
  selectedGroups,
  togglePick,
  unknownPicks,
  withoutUnknown,
} from "./deck-view";

const PREVIEW = fixture as DeckPreviewResponse;

const signal = (id: string, kind: InsightsBrief["signals"][number]["kind"], title = id) =>
  ({ id, kind, title, status: "emerging", claim_type: "observed" }) as InsightsBrief["signals"][number];
const BRIEF = {
  signals: [signal("price-ceiling", "emerging_signal", "Price ceiling"), signal("loyalty-lapse", "risk_blocker", "Loyalty lapse"), signal("legacy", null)],
  opportunities: [{ id: "O2", title: "Premium personalization tier", status: "supported", thesis_claim_type: "hypothesis" }],
} as unknown as Pick<InsightsBrief, "signals" | "opportunities">;
const ANALYSES = [
  { id: "wtp", title: "Willingness to pay", status: "computed", business_area: "Willingness to pay" },
  { id: "broken", title: "Broken", status: "mismatch", business_area: null },
] as unknown as Analysis[];

const urlParams = (href: string) => new URL(href, "http://x").searchParams;

describe("selection", () => {
  it("round-trips through the deck URL with picker toggles", () => {
    let pick = parseDeckSelection(urlParams("/w/N/insights/deck?s=price-ceiling&o=O2"));
    pick = togglePick(pick, "analyses", "a b&c");
    pick = togglePick(pick, "signals", "loyalty-lapse");
    pick = togglePick(pick, "opportunities", "O2");
    expect(pick).toEqual({ signals: ["price-ceiling", "loyalty-lapse"], opportunities: [], analyses: ["a b&c"] });
    expect(parseDeckSelection(urlParams(pickHref("N", pick)))).toEqual(pick);
    expect(pickHref("N", EMPTY_PICK)).toBe("/w/N/insights/deck");
  });

  it("toggles without mutating and respects server limits", () => {
    const start = { ...EMPTY_PICK, signals: ["a"] };
    const next = togglePick(start, "signals", "a");
    expect(start.signals).toEqual(["a"]);
    expect(next.signals).toEqual([]);
    expect(pickSize({ signals: ["a"], opportunities: ["b"], analyses: ["c"] })).toBe(3);
    const full = { ...EMPTY_PICK, opportunities: Array.from({ length: 10 }, (_, i) => `O${i}`) };
    expect(canAdd(full, "opportunities")).toBe(false);
    expect(canAdd(full, "signals")).toBe(true);
  });

  it("separates ids the workspace no longer knows", () => {
    const known = knownIds(BRIEF, ANALYSES);
    const pick = { signals: ["price-ceiling", "gone"], opportunities: ["O2"], analyses: ["nope"] };
    expect(unknownPicks(pick, known)).toEqual({ signals: ["gone"], opportunities: [], analyses: ["nope"] });
    expect(withoutUnknown(pick, known)).toEqual({ signals: ["price-ceiling"], opportunities: ["O2"], analyses: [] });
  });

  it("builds the request body with trimmed, optional text", () => {
    const pick = { signals: ["s"], opportunities: [], analyses: [] };
    expect(deckRequest(pick, "  ", "")).toEqual({ signal_ids: ["s"], opportunity_ids: [], analysis_ids: [] });
    expect(deckRequest(pick, " Board deck ", " Why? ")).toMatchObject({ title: "Board deck", question: "Why?" });
    expect(deckRequest(pick, "x".repeat(200), "").title).toHaveLength(120);
  });
});

describe("pickerGroups", () => {
  it("groups opportunities, insights by category and analyses, dropping empty groups", () => {
    const groups = pickerGroups(BRIEF, ANALYSES);
    expect(groups.map((g) => g.label)).toEqual([
      "Growth opportunities",
      "Emerging Signals",
      "Risks / Blockers",
      "Other findings",
      "Analyses",
    ]);
    const analyses = groups.at(-1)!.items;
    expect(analyses[0]).toMatchObject({ claim: "derived", hint: "Willingness to pay" });
    expect(analyses[1]).toMatchObject({ claim: null, hint: "Figures not computed" });
  });

  it("narrows to the selected items", () => {
    const groups = selectedGroups(pickerGroups(BRIEF, ANALYSES), { signals: ["loyalty-lapse"], opportunities: [], analyses: ["wtp"] });
    expect(groups.map((g) => [g.label, g.items.map((i) => i.id)])).toEqual([
      ["Risks / Blockers", ["loyalty-lapse"]],
      ["Analyses", ["wtp"]],
    ]);
  });

  it("is empty without data", () => {
    expect(pickerGroups(undefined, undefined)).toEqual([]);
  });
});

describe("deckOutline", () => {
  it("derives the sections from the server preview, in order", () => {
    const outline = deckOutline(PREVIEW.deck);
    expect(outline.map((s) => s.label)).toEqual([
      "Title",
      "Executive summary",
      "Key customer findings",
      "Quantitative evidence",
      "Growth opportunities",
      "Next steps",
      "Sources",
    ]);
    const quant = outline[3];
    expect(quant.slides).toEqual([4, 5]);
    expect(quant.titles).toEqual(["Willingness to pay by segment"]);
    expect(outline[4].titles).toEqual(["Premium personalization tier"]);
  });

  it("folds continuation slides into one section", () => {
    const slide = (index: number, title: string) => ({ index, kind: "risks" as const, title, subtitle: null, blocks: [], notes: [] });
    const outline = deckOutline({ slides: [slide(1, "Risks and blockers"), slide(2, "Risks and blockers (cont.)")] });
    expect(outline).toEqual([{ kind: "risks", label: "Risks and blockers", slides: [1, 2], titles: [] }]);
  });
});

describe("exclusions and errors", () => {
  it("names excluded items by title with the server's reason", () => {
    const views = exclusionViews(PREVIEW.deck.excluded, pickerGroups(BRIEF, ANALYSES));
    expect(views).toEqual([{ id: "loyalty-lapse", title: "Loyalty lapse", reason: "Its main claim no longer has verified support." }]);
    expect(exclusionViews([{ id: "zz", reason: "r" }], [])[0].title).toBe("A selected finding");
  });

  it("explains deck failures without codes", () => {
    expect(deckErrorMessage(new ApiError(422, "DECK_EMPTY", "x"))).toMatch(/nothing to put in a presentation/);
    expect(deckErrorMessage(new ApiError(422, "DECK_TOO_LARGE", "x"))).toMatch(/too large/);
    expect(deckErrorMessage(new Error("boom"))).not.toMatch(/boom|UNKNOWN/);
  });
});

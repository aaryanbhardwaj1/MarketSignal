import { describe, expect, it } from "vitest";
import type { CitationCard } from "./api/types";
import {
  PLACEHOLDER_CLOSE,
  PLACEHOLDER_OPEN,
  prepareMarkdown,
  splitPlaceholders,
  stripInference,
  tokenizeMarkers,
} from "./citations";
import type { AliasCitation } from "./run-stream";

const H1 = "NORTHSTAR/SURVEY-2026@v1:R185";
const H2 = "NORTHSTAR/Q3-REVIEW@v1:SL6.N1";

const card = (handle: string, title: string): CitationCard => ({
  handle,
  source_code: handle.split("/")[1].split("@")[0],
  source_title: title,
  source_class: "customer",
  source_type: "csv",
  locator_label: "Row 185",
  anchor_child_id: "child-1",
  char_start: 0,
  char_end: 4,
  parent_content_hash: null,
});

const alias = (name: string, handle = H1): AliasCitation => ({
  alias: name,
  handle,
  source_title: "Survey",
  source_class: "customer",
  locator_label: "Row 185",
});

describe("tokenizeMarkers: draft aliases", () => {
  it("turns a bound alias into a chip", () => {
    const out = tokenizeMarkers("Up 12% [E1].", { aliases: { E1: alias("E1") } });
    expect(out).toEqual([
      { kind: "text", text: "Up 12% " },
      { kind: "alias", alias: "E1", citation: alias("E1") },
      { kind: "text", text: "." },
    ]);
  });

  it("drops an alias with no citation event, including the space before it", () => {
    expect(tokenizeMarkers("Up 12% [E9].", { aliases: {} })).toEqual([{ kind: "text", text: "Up 12%." }]);
    expect(tokenizeMarkers("a [E9] b")).toEqual([{ kind: "text", text: "a b" }]);
  });

  it("keeps lowercase / spaced lookalikes as literal text", () => {
    expect(tokenizeMarkers("see [e3] and [E 3]")).toEqual([{ kind: "text", text: "see [e3] and [E 3]" }]);
  });

  it("handles adjacent markers", () => {
    const out = tokenizeMarkers("x [E1][E2][E3]", { aliases: { E1: alias("E1"), E3: alias("E3", H2) } });
    expect(out.map((s) => s.kind)).toEqual(["text", "alias", "alias"]);
    expect(out[2]).toMatchObject({ alias: "E3" });
  });
});

describe("tokenizeMarkers: canonical handles", () => {
  const cards = [card(H1, "Survey"), card(H2, "Q3 review")];

  it("binds a handle to its card", () => {
    const out = tokenizeMarkers(`Growth [[${H1}]].`, { cards });
    expect(out[1]).toEqual({ kind: "handle", handle: H1, card: cards[0] });
    expect(out[2]).toEqual({ kind: "text", text: "." });
  });

  it("marks a handle without a card as unverified (card: null)", () => {
    const out = tokenizeMarkers("x [[NORTHSTAR/OTHER@v2:p1]]", { cards });
    expect(out[1]).toEqual({ kind: "handle", handle: "NORTHSTAR/OTHER@v2:p1", card: null });
  });

  it("splits adjacent handles and keeps surrounding punctuation", () => {
    const out = tokenizeMarkers(`(${"a"} [[${H1}]][[${H2}]]), end;`, { cards });
    expect(out).toEqual([
      { kind: "text", text: "(a " },
      { kind: "handle", handle: H1, card: cards[0] },
      { kind: "handle", handle: H2, card: cards[1] },
      { kind: "text", text: "), end;" },
    ]);
  });

  it("does not treat single brackets or [inference]-less text as markers", () => {
    expect(tokenizeMarkers("[see note] [1]")).toEqual([{ kind: "text", text: "[see note] [1]" }]);
  });

  it("lifts [inference] tags out as tokens", () => {
    const out = tokenizeMarkers("Likely rising [inference].");
    expect(out).toEqual([
      { kind: "text", text: "Likely rising " },
      { kind: "inference" },
      { kind: "text", text: "." },
    ]);
  });
});

describe("prepareMarkdown / splitPlaceholders", () => {
  it("round-trips markers through placeholders that Markdown cannot reinterpret", () => {
    const prepared = prepareMarkdown(`**Up** [[${H1}]](http://x) [E9]`, { cards: [card(H1, "Survey")] });
    expect(prepared.source).toBe(`**Up** ${PLACEHOLDER_OPEN}0${PLACEHOLDER_CLOSE}(http://x)`);
    expect(prepared.tokens).toHaveLength(1);
    expect(splitPlaceholders(`a ${PLACEHOLDER_OPEN}0${PLACEHOLDER_CLOSE}${PLACEHOLDER_OPEN}1${PLACEHOLDER_CLOSE}.`)).toEqual([
      { kind: "text", text: "a " },
      { kind: "chip", index: 0 },
      { kind: "chip", index: 1 },
      { kind: "text", text: "." },
    ]);
  });

  it("strips stray private-use characters from the input", () => {
    const prepared = prepareMarkdown(`spoof ${PLACEHOLDER_OPEN}0${PLACEHOLDER_CLOSE}`);
    expect(prepared.source).toBe("spoof 0");
    expect(prepared.tokens).toEqual([]);
  });
});

describe("stripInference", () => {
  it("removes the tag before terminal punctuation", () => {
    expect(stripInference("Demand will likely grow [inference].")).toEqual({
      text: "Demand will likely grow.",
      inferred: true,
    });
  });

  it("handles a trailing tag and case/whitespace variants", () => {
    expect(stripInference("Probably true [ Inference ]")).toEqual({ text: "Probably true", inferred: true });
  });

  it("leaves untagged units alone", () => {
    expect(stripInference(`Up 12% [[${H1}]].`)).toEqual({ text: `Up 12% [[${H1}]].`, inferred: false });
  });
});

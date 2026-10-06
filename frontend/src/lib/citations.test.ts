import { describe, expect, it } from "vitest";
import type { CitationCard, ResultCitationCard } from "./api/types";
import {
  PLACEHOLDER_CLOSE,
  PLACEHOLDER_OPEN,
  prepareMarkdown,
  splitPlaceholders,
  stripInference,
  tokenizeMarkers,
} from "./citations";
import type { AliasCitation, ResultAliasCitation } from "./run-stream";

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

const RID = "3f2b7c9e-8a41-4d6b-b0a1-5c2d9e7f1a30";
const RID2 = "9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f";

const resultCard = (id = RID): ResultCitationCard => ({
  kind: "result",
  result_id: id,
  source_code: "SURVEY-2026",
  dataset: "SURVEY-2026:1",
  source_version: 1,
  table: "Survey",
  op: "aggregate",
  summary: "mean(nps) by region",
  handle: "NORTHSTAR/SURVEY-2026@v1",
});

const resultAlias = (name: string, id = RID): ResultAliasCitation => ({
  kind: "result",
  alias: name,
  result_id: id,
  source_code: "SURVEY-2026",
  dataset: "SURVEY-2026:1",
  op: "aggregate",
  summary: "mean(nps) by region",
});

describe("tokenizeMarkers: computed results", () => {
  it("binds [[result:<uuid>]] to its result card", () => {
    const cards = [resultCard()];
    const out = tokenizeMarkers(`NPS is 41 [[result:${RID}]].`, { cards });
    expect(out).toEqual([
      { kind: "text", text: "NPS is 41 " },
      { kind: "result", resultId: RID, ref: cards[0] },
      { kind: "text", text: "." },
    ]);
  });

  it("still yields a result chip (no summary) when the card is missing", () => {
    const out = tokenizeMarkers(`x [[result:${RID}]]`);
    expect(out[1]).toEqual({ kind: "result", resultId: RID, ref: null });
  });

  it("treats a result marker with a non-uuid id as an unverified handle, never a result", () => {
    const out = tokenizeMarkers("x [[result:not-a-uuid]]");
    expect(out[1]).toEqual({ kind: "handle", handle: "result:not-a-uuid", card: null });
  });

  it("matches the result prefix case-sensitively", () => {
    const out = tokenizeMarkers(`x [[Result:${RID}]]`);
    expect(out[1]).toMatchObject({ kind: "handle", card: null });
  });

  it("never lets a result card satisfy an evidence handle (or vice versa)", () => {
    const cards = [resultCard(), card(H1, "Survey")];
    const out = tokenizeMarkers(`[[${H1}]] [[NORTHSTAR/SURVEY-2026@v1]]`, { cards });
    expect(out[0]).toMatchObject({ kind: "handle", card: cards[1] });
    expect(out[2]).toMatchObject({ kind: "handle", card: null });
  });

  it("binds [R1] only from a result citation event", () => {
    const out = tokenizeMarkers("Up [R1] and [E1].", {
      aliases: { R1: resultAlias("R1"), E1: alias("E1") },
    });
    expect(out.map((s) => s.kind)).toEqual(["text", "result", "text", "alias", "text"]);
    expect(out[1]).toMatchObject({ kind: "result", resultId: RID });
  });

  it("drops an unannounced [R#] with the whitespace before it, like [E#]", () => {
    expect(tokenizeMarkers("Up 12% [R9].", { aliases: {} })).toEqual([{ kind: "text", text: "Up 12%." }]);
  });

  it("does not confuse alias families: [R1] bound to evidence and [E1] bound to a result render nothing", () => {
    const out = tokenizeMarkers("a [R1] b [E1]", { aliases: { R1: alias("R1"), E1: resultAlias("E1") } });
    expect(out).toEqual([{ kind: "text", text: "a b" }]);
  });

  it("keeps lowercase [r1] as literal text", () => {
    expect(tokenizeMarkers("see [r1]")).toEqual([{ kind: "text", text: "see [r1]" }]);
  });

  it("round-trips result chips through prepareMarkdown", () => {
    const prepared = prepareMarkdown(`41 [[result:${RID}]] [[result:${RID2}]]`, { cards: [resultCard()] });
    expect(prepared.tokens.map((t) => t.kind)).toEqual(["result", "result"]);
    expect(prepared.source).toBe(`41 ${PLACEHOLDER_OPEN}0${PLACEHOLDER_CLOSE} ${PLACEHOLDER_OPEN}1${PLACEHOLDER_CLOSE}`);
  });
});

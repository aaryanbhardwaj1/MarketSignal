import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { CitationCard } from "@/lib/api/types";
import { SafeMarkdown } from "./safe-markdown";

const HANDLE = "NORTHSTAR/SURVEY-2026@v1:R185";
const CARD: CitationCard = {
  handle: HANDLE,
  source_code: "SURVEY-2026",
  source_title: "Consumer survey",
  source_class: "customer",
  source_type: "csv",
  locator_label: "Row 185",
  anchor_child_id: "0d4c7f8e-2b5a-4c1e-9a77-1f2e3d4c5b6a",
  char_start: 0,
  char_end: 4,
  parent_content_hash: null,
};

const render = (text: string, props: Partial<Parameters<typeof SafeMarkdown>[0]> = {}) =>
  renderToStaticMarkup(<SafeMarkdown text={text} ws="NORTHSTAR" {...props} />);

describe("SafeMarkdown", () => {
  it("renders the allowed Markdown subset", () => {
    const html = render("### Answer\n\n**Bold** and *em* with `code`\n\n- one\n- two\n\n> quote");
    expect(html).toContain("<h3");
    expect(html).toContain("<strong>Bold</strong>");
    expect(html).toContain("<em>em</em>");
    expect(html).toContain("<code");
    expect(html).toContain("<ul");
    expect(html).toContain("<blockquote");
  });

  it("strips images entirely", () => {
    const html = render("before ![alt text](http://evil.example/x.png) after");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("evil.example");
    expect(html).toContain("before");
    expect(html).toContain("after");
  });

  it("skips raw HTML", () => {
    const html = render('hi <img src=x onerror="alert(1)"> <script>alert(2)</script><b>bold</b>');
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("onerror");
    expect(html).not.toContain("<b>");
    expect(html).toContain("hi");
  });

  it("renders links as their text only", () => {
    const html = render("see [the report](javascript:alert(1)) and <https://example.com>");
    expect(html).not.toMatch(/<a[\s>]/);
    expect(html).not.toContain("javascript:");
    expect(html).toContain("the report");
  });

  it("maps disallowed headings to allowed ones", () => {
    const html = render("## Key findings\n\ntext");
    expect(html).toContain("<h3");
    expect(html).not.toContain("<h2");
  });

  it("renders a canonical marker with a card as a chip linking to the evidence viewer", () => {
    const html = render(`Growth is up [[${HANDLE}]].`, { citations: { cards: [CARD] } });
    expect(html).toContain("Consumer survey · Row 185");
    expect(html).toContain(
      `href="/w/NORTHSTAR/evidence?h=${encodeURIComponent(HANDLE)}&amp;child=${CARD.anchor_child_id}"`,
    );
    expect(html).not.toContain(`[[${HANDLE}]]`);
  });

  it("renders a marker without a card as an inert unverified chip", () => {
    const html = render("Claim [[NORTHSTAR/GONE@v1:p1]].", { citations: { cards: [CARD] } });
    expect(html).toContain("unverified");
    expect(html).not.toContain("NORTHSTAR/GONE");
    expect(html).not.toMatch(/<a[\s>]/);
  });

  it("renders draft aliases only when bound by a citation event", () => {
    const aliases = {
      E1: {
        alias: "E1",
        handle: HANDLE,
        source_title: "Consumer survey",
        source_class: "customer",
        locator_label: "Row 185",
      },
    };
    const html = render("Known [E1], unknown [E7].", { citations: { aliases } });
    expect(html).toContain("Consumer survey · Row 185");
    expect(html).not.toContain("[E1]");
    expect(html).not.toContain("E7");
  });

  it("keeps chips intact inside emphasis and lists", () => {
    const html = render(`- **Up [[${HANDLE}]]**`, { citations: { cards: [CARD] } });
    expect(html).toContain("<li");
    expect(html).toContain("Consumer survey · Row 185");
  });

  it("shows [inference] as a label instead of the raw tag", () => {
    const html = render("Demand may rise [inference].");
    expect(html).toContain("Inference");
    expect(html).not.toContain("[inference]");
  });

  it("renders inline units without block elements", () => {
    const html = render(`One sentence [[${HANDLE}]].`, { inline: true, citations: { cards: [CARD] } });
    expect(html.startsWith("<span")).toBe(true);
    expect(html).not.toContain("<p");
  });
});

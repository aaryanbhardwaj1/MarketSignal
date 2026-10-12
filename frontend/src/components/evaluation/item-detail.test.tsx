import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import itemsJson from "@/lib/api/__fixtures__/evaluation-items-p3-grounded-live.json";
import type { EvalItem, EvalItemsPage } from "@/lib/api/contracts";
import { ItemDetail } from "./item-detail";

const page = itemsJson as unknown as EvalItemsPage;
const grounded = page.items.find((i) => i.phase === "grounded" && i.failure) as Extract<EvalItem, { phase: "grounded" }>;

describe("ItemDetail", () => {
  it("shows the labelled failure, the stored answer and non-interactive citation labels", () => {
    const html = renderToStaticMarkup(<ItemDetail item={grounded} provenance={null} />);
    expect(html).toContain("Labelled failure");
    expect(html).toContain("Root cause.");
    expect(html).toContain("Model reasoning is not recorded");
    expect(html).not.toContain("<button");
    expect(html).not.toContain("[[");
    expect(html).toContain(">SUPPORT-THEMES<");
  });

  it("renders stored markup as text, never as HTML", () => {
    const item = { ...grounded, failure: null, answer_markdown: 'Hello <img src=x onerror="alert(1)"> [[WS/DOC@v1:P1]]' };
    const html = renderToStaticMarkup(<ItemDetail item={item} provenance={null} />);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});

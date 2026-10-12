import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { runMode } from "@/lib/labels";
import { QuestionForm } from "./question-form";

const html = renderToStaticMarkup(<QuestionForm disabled={false} busy={false} onSubmit={async () => true} />);

describe("QuestionForm mode selector", () => {
  it("renders an accessible radio group with Auto selected by default", () => {
    expect(html).toContain("<fieldset");
    expect(html).toContain("<legend");
    const radios = html.match(/<input[^>]*type="radio"[^>]*>/g) ?? [];
    expect(radios).toHaveLength(3);
    const checked = radios.filter((r) => / checked=""/.test(r));
    expect(checked).toHaveLength(1);
    expect(checked[0]).toContain('value="auto"');
  });

  it("describes each mode", () => {
    for (const code of ["auto", "standard", "research"]) expect(html).toContain(runMode(code).label);
    expect(html).toContain("Fast answer from the current evidence base.");
    expect(html).toContain("Searches across multiple sources and analysis tools before answering.");
    expect(html).toContain(`questions that need calculations get ${runMode("research").label}`);
    expect(html).toMatch(/aria-describedby="[^"]+"/);
  });

  it("keeps the question box and submit button", () => {
    expect(html).toContain('id="chat-question"');
    expect(html).toContain(">Ask<");
  });
});

describe("QuestionForm while a question is being answered", () => {
  const locked = renderToStaticMarkup(<QuestionForm disabled={false} locked busy={false} onSubmit={async () => true} />);
  it("keeps the box focusable (read-only, aria-disabled) instead of disabling it", () => {
    const box = locked.match(/<textarea[^>]*>/)?.[0] ?? "";
    expect(box.toLowerCase()).toContain("readonly");
    expect(box).toContain('aria-disabled="true"');
    expect(box).not.toMatch(/ disabled=""/);
  });
});

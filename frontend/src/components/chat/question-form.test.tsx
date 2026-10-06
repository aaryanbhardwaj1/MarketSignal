import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
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
    expect(html).toContain("Auto");
    expect(html).toContain("Standard");
    expect(html).toContain("Research");
    expect(html).toContain("One evidence search");
    expect(html).toContain("Multi-step agent with tool calls");
    expect(html).toContain("Deterministic routing");
    expect(html).toMatch(/aria-describedby="[^"]+"/);
  });

  it("keeps the question box and submit button", () => {
    expect(html).toContain('id="chat-question"');
    expect(html).toContain(">Ask<");
  });
});

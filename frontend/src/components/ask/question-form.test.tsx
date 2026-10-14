import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { runMode } from "@/lib/labels";
import { COMPOSER_MODE_HELP, composerKeySends, COUNTER_THRESHOLD, MAX_QUESTION_LENGTH, QuestionForm, showCounter } from "./question-form";

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

  it("describes each mode in plain words", () => {
    for (const code of ["auto", "standard", "research"]) expect(html).toContain(runMode(code).label);
    for (const help of Object.values(COMPOSER_MODE_HELP)) expect(html).toContain(help);
    expect(COMPOSER_MODE_HELP.research).toContain("Slower");
    expect(html).toMatch(/aria-describedby="[^"]+"/);
    expect(html).toContain('aria-label="About answer modes"');
  });

  it("keeps the question box and an icon send button", () => {
    expect(html).toContain('id="chat-question"');
    expect(html).toContain('aria-label="Send question"');
    // Empty question: nothing to send.
    expect(html).toMatch(/<button type="submit" disabled=""/);
  });
});

describe("QuestionForm floating surface", () => {
  it("uses the floating radius and overlay shadow", () => {
    expect(html).toContain("rounded-float");
    expect(html).toContain("shadow-overlay");
  });

  it("shows the attach control only when attaching is wired", () => {
    expect(html).not.toContain("Attach files");
    const withAttach = renderToStaticMarkup(<QuestionForm disabled busy={false} onSubmit={async () => true} onAttach={() => {}} />);
    expect(withAttach).toContain('aria-label="Attach files"');
    expect(withAttach).toMatch(/type="file"[^>]*accept="\.pdf,\.docx,\.pptx,\.xlsx,\.csv,\.md,\.markdown,\.txt"/);
    // Offline: the box and send are disabled, attaching is not.
    expect(withAttach).toMatch(/<textarea[^>]* disabled=""/);
    expect(withAttach).not.toMatch(/aria-label="Attach files"[^>]* disabled=""/);
  });
});

describe("QuestionForm character counter", () => {
  it("appears only near the limit", () => {
    expect(showCounter(0)).toBe(false);
    expect(showCounter(COUNTER_THRESHOLD - 1)).toBe(false);
    expect(showCounter(COUNTER_THRESHOLD)).toBe(true);
    expect(html).not.toMatch(new RegExp(`>\\d+/${MAX_QUESTION_LENGTH}<`)); // (svg xmlns also holds "/2000")
    const long = renderToStaticMarkup(
      <QuestionForm disabled={false} busy={false} onSubmit={async () => true} initialText={"x".repeat(COUNTER_THRESHOLD)} />,
    );
    expect(long).toContain(`${COUNTER_THRESHOLD}/${MAX_QUESTION_LENGTH}`);
  });
});

describe("composerKeySends", () => {
  const key = (over: Partial<Parameters<typeof composerKeySends>[0]>) =>
    composerKeySends({ key: "Enter", shiftKey: false, metaKey: false, ctrlKey: false, isComposing: false, ...over });

  it("sends on Enter and Cmd/Ctrl+Enter", () => {
    expect(key({})).toBe(true);
    expect(key({ metaKey: true })).toBe(true);
    expect(key({ ctrlKey: true })).toBe(true);
  });

  it("keeps Shift+Enter for a new line and ignores IME composition and other keys", () => {
    expect(key({ shiftKey: true })).toBe(false);
    expect(key({ isComposing: true })).toBe(false);
    expect(key({ key: "a" })).toBe(false);
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

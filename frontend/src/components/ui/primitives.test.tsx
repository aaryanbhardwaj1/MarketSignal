import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { Badge } from "./badge";
import { BarList } from "./bar-list";
import { Callout } from "./callout";
import { CiteChip, InferenceTag } from "./cite-chip";
import { DevDetails } from "./disclosure";
import { Button } from "./button";
import { Select } from "./form-controls";
import { ResultPanel } from "./result-panel";
import { ErrorState, EmptyState } from "./states";
import { StatusIndicator } from "./status-indicator";
import { normalizeTone } from "./tone";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("tones", () => {
  it("maps legacy lib/status tones onto the design-system tones", () => {
    expect(normalizeTone("warning")).toBe("warn");
    expect(normalizeTone("progress")).toBe("info");
    expect(normalizeTone("muted")).toBe("neutral");
    expect(normalizeTone("success")).toBe("success");
    expect(normalizeTone(undefined)).toBe("neutral");
  });

  it("Badge accepts both legacy and new tones", () => {
    expect(html(<Badge tone="warning">Degraded</Badge>)).toContain("bg-warn-subtle");
    expect(html(<Badge tone="accent">New</Badge>)).toContain("bg-accent-subtle");
  });
});

describe("status is never colour alone", () => {
  it("StatusIndicator always prints its label", () => {
    const out = html(<StatusIndicator tone="danger" label="Failed" detail="2 minutes ago" />);
    expect(out).toContain("Failed");
    expect(out).toContain("2 minutes ago");
    expect(out).toContain('aria-hidden="true"');
  });

  it("Callout names its tone for assistive tech", () => {
    const out = html(<Callout tone="warn" title="Live model unavailable" />);
    expect(out).toContain('<span class="sr-only">Warning: </span>');
    expect(html(<Callout tone="danger" title="x" />)).toContain('role="alert"');
  });
});

describe("CiteChip", () => {
  it("is a button with a descriptive accessible name, never a link", () => {
    const out = html(<CiteChip kind="evidence" index={3} label="Customer survey 2026" onOpen={() => undefined} />);
    expect(out).toContain("<button");
    expect(out).not.toContain("href=");
    expect(out).toContain('aria-label="Evidence 3: Customer survey 2026"');
  });

  it("spells out non-verified states and labels computed results", () => {
    const out = html(<CiteChip kind="result" index={1} label="Mean NPS" state="unverified" onOpen={() => undefined} />);
    expect(out).toContain("Computed 1");
    expect(out).toContain("not verified");
    expect(html(<InferenceTag />)).toContain("Inference");
  });
});

describe("states", () => {
  it("ErrorState derives a plain message from an error and keeps the code inside Technical details", () => {
    const out = html(<ErrorState title="Could not load the run" error={new ApiError(404, "RUN_NOT_FOUND", "run x not found")} />);
    expect(out).toContain("That research run could not be found.");
    const summaryAt = out.indexOf("Technical details");
    expect(summaryAt).toBeGreaterThan(-1);
    expect(out.indexOf("RUN_NOT_FOUND")).toBeGreaterThan(summaryAt);
    expect(out).not.toContain("run x not found");
  });

  it("ErrorState renders no empty action row without a retry", () => {
    const out = html(<ErrorState title="x" description="y" devDetail="CODE" />);
    expect(out).not.toContain("mt-3 flex");
    expect(out).not.toContain("Try again");
  });

  it("EmptyState and ErrorState render their copy", () => {
    expect(html(<EmptyState title="No conversations yet" description="Ask a question to start." />)).toContain(
      "No conversations yet",
    );
    expect(html(<ErrorState title="Could not load runs" description="Try again." />)).toContain('role="alert"');
  });

  it("DevDetails pretty-prints data", () => {
    const out = html(<DevDetails data={{ handle: "NORTHSTAR/X@v1:P1" }} />);
    expect(out).toContain("Technical details");
    expect(out).toContain("&quot;handle&quot;: &quot;NORTHSTAR/X@v1:P1&quot;");
  });
});

describe("controls", () => {
  it("a loading Button stays focusable (aria-disabled), while `disabled` is native", () => {
    const loading = html(<Button loading>Load more</Button>);
    expect(loading).toContain('aria-disabled="true"');
    expect(loading).not.toMatch(/\sdisabled=""/);
    expect(html(<Button disabled>Ask</Button>)).toMatch(/\sdisabled=""/);
  });

  it("Select draws its own chevron instead of the native one", () => {
    const out = html(<Select id="s" options={[{ value: "a", label: "A" }]} />);
    expect(out).toContain("appearance-none");
    expect(out).toContain("<svg");
  });

  it("InferenceTag explains itself", () => {
    expect(html(<InferenceTag />)).toContain("not stated directly in a source");
  });
});

describe("ResultPanel", () => {
  it("shows the table in words and skips one that repeats the source title", () => {
    const panel = (table: string, sourceTitle = "Northstar Product Performance") =>
      html(<ResultPanel title="t" unit="" provenance={{ sourceTitle, sourceCode: "PP", version: 2, table }} />);
    expect(panel("SKU_Performance")).toContain("From Northstar Product Performance · Version 2 · SKU performance");
    expect(panel("SKU_Performance")).not.toContain("SKU_Performance");
    expect(panel("Product_Performance")).not.toContain("· Product performance");
  });
});

describe("BarList", () => {
  it("renders an ordered list with printed values and proportional bars", () => {
    const out = html(
      <BarList
        ariaLabel="Sources by class"
        items={[
          { label: "Customer", value: 8, display: "8" },
          { label: "Market", value: 2, display: "2", emphasis: true },
        ]}
      />,
    );
    expect(out).toContain('<ol aria-label="Sources by class"');
    expect(out).toContain("width:100%");
    expect(out).toContain("width:25%");
  });

  it("handles an all-zero list without dividing by zero", () => {
    expect(html(<BarList ariaLabel="x" items={[{ label: "A", value: 0, display: "0" }]} />)).toContain("width:0%");
  });
});

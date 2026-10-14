import { Search } from "lucide-react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Button } from "./button";
import { Card } from "./card";
import { CiteChip } from "./cite-chip";
import { CLAIM_DEFINITION, CLAIM_LABEL, ClaimTag, type ClaimType } from "./claim-tag";
import { Disclosure } from "./disclosure";
import { Divider } from "./divider";
import { NotRun } from "./not-run";
import { PageHeader } from "./page-header";
import { SectionHeader } from "./section-header";
import { Stat, StatRow } from "./stat";
import { EmptyState, ErrorState } from "./states";
import { EVIDENCE_STATUS_LABEL, isEvidenceStatus, StatusPill, type EvidenceStatus } from "./status-pill";
import { Table } from "./table";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("ClaimTag", () => {
  const cases: Array<[ClaimType, string]> = [
    ["observed", "Observed"],
    ["derived", "Derived"],
    ["inference", "Inference"],
    ["hypothesis", "Hypothesis"],
    ["forecast", "Forecast"],
  ];

  it.each(cases)("%s renders the exact label %s", (type, label) => {
    expect(CLAIM_LABEL[type]).toBe(label);
    expect(html(<ClaimTag type={type} />)).toContain(`>${label}<`);
  });

  it("dashes interpretive and forward-looking claims, keeps observed and derived solid", () => {
    for (const type of ["inference", "hypothesis", "forecast"] as const) {
      expect(html(<ClaimTag type={type} />)).toContain("border-dashed");
    }
    for (const type of ["observed", "derived"] as const) {
      const out = html(<ClaimTag type={type} />);
      expect(out).toContain("border-solid");
      expect(out).not.toContain("border-dashed");
    }
  });

  it("always exposes the definition to assistive tech", () => {
    expect(html(<ClaimTag type="hypothesis" />)).toContain(`<span class="sr-only">: ${CLAIM_DEFINITION.hypothesis}</span>`);
    const explained = html(<ClaimTag type="forecast" explain />);
    expect(explained).toContain('role="tooltip"');
    expect(explained).toContain(CLAIM_DEFINITION.forecast);
    expect(explained).toContain('tabindex="0"');
    expect(explained).toContain("aria-describedby=");
  });
});

describe("StatusPill", () => {
  const cases: Array<[EvidenceStatus, string]> = [
    ["strong_evidence", "Strong evidence"],
    ["supported", "Supported"],
    ["emerging", "Emerging"],
    ["mixed_evidence", "Mixed evidence"],
    ["needs_validation", "Needs validation"],
    ["needs_research", "Needs validation"],
  ];

  it.each(cases)("%s reads %s", (status, label) => {
    expect(EVIDENCE_STATUS_LABEL[status]).toBe(label);
    const out = html(<StatusPill status={status} />);
    expect(out).toContain(label);
    expect(out).toContain('aria-hidden="true"');
  });

  it("never shows a numeric score and guards unknown keys", () => {
    expect(html(<StatusPill status="supported" />).replace(/<[^>]*>/g, "")).toBe("Supported");
    expect(isEvidenceStatus("supported")).toBe(true);
    expect(isEvidenceStatus("high_confidence")).toBe(false);
  });
});

describe("Stat", () => {
  it("prints label, tabular value, sub line and a worded delta", () => {
    const out = html(
      <Stat label="Repeat purchase rate" value="34%" sub="of 600 customers" delta={{ label: "+4 pts vs. 2025", direction: "up", sentiment: "positive" }} />,
    );
    expect(out).toContain("Repeat purchase rate");
    expect(out).toContain("tabular-nums");
    expect(out).toContain("34%");
    expect(out).toContain("of 600 customers");
    expect(out).toContain("+4 pts vs. 2025");
    expect(out).toContain("text-success");
  });

  it("sizes the value and renders the trend slot", () => {
    expect(html(<Stat label="x" value="1" size="lg" />)).toContain("text-display");
    expect(html(<Stat label="x" value="1" size="sm" />)).toContain("text-lg");
    expect(html(<Stat label="x" value="1" trend={<svg data-testid="spark" />} />)).toContain('data-testid="spark"');
  });

  it("omits the delta row when there is nothing to say", () => {
    expect(html(<Stat label="x" value="1" />)).not.toContain("mt-1 flex flex-wrap");
    expect(html(<StatRow><Stat label="a" value="1" /></StatRow>)).toContain("divide-x");
  });
});

describe("NotRun", () => {
  it("is a neutral dashed note with no number and no alert role", () => {
    const out = html(<NotRun reason="The test split has not been evaluated." />);
    expect(out).toContain("Not yet run");
    expect(out).toContain("The test split has not been evaluated.");
    expect(out).toContain("border-dashed");
    expect(out).toContain('role="note"');
    expect(out).not.toContain('role="alert"');
    expect(out).not.toContain("danger");
  });

  it("accepts a custom title and detail", () => {
    const out = html(<NotRun title="Evaluation not yet run" reason="Run it from the CLI." detail="Last baseline: none" />);
    expect(out).toContain("Evaluation not yet run");
    expect(out).toContain("Last baseline: none");
  });
});

describe("states", () => {
  it("EmptyState renders an optional icon, teaching sentence and action", () => {
    const out = html(<EmptyState icon={Search} title="No sources match" description="Try a broader term." action={<button>Clear</button>} />);
    expect(out).toContain("<svg");
    expect(out).toContain("Try a broader term.");
    expect(out).toContain("<button>Clear</button>");
    expect(html(<EmptyState title="x" />)).not.toContain("<svg");
    expect(html(<EmptyState title="x" size="sm" />)).toContain("py-6");
  });

  it("ErrorState is calm: hairline surface, danger only on the icon", () => {
    const out = html(<ErrorState title="Could not load runs" retry={() => undefined} />);
    expect(out).toContain('role="alert"');
    expect(out).toContain("border-border");
    expect(out).not.toContain("bg-danger-subtle");
    expect(out).toContain("Try again");
  });
});

describe("restyled primitives", () => {
  it("Button has a quiet variant", () => {
    expect(html(<Button variant="quiet">View all</Button>)).toContain("text-accent-text");
  });

  it('Card variant="plain" is just a section without border or padding', () => {
    const out = html(<Card variant="plain" as="section">Body</Card>);
    expect(out).toMatch(/^<section class="">Body<\/section>$/);
    expect(html(<Card>Body</Card>)).toContain("border-border");
    expect(html(<Card variant="raised">Body</Card>)).toContain("shadow-raised");
  });

  it("Table can pin its header inside a scroll frame", () => {
    const out = html(
      <Table caption="Runs" rows={[{ id: "a" }]} rowKey={(r) => r.id} columns={[{ key: "id", header: "Id", cell: (r) => r.id }]} stickyHeader maxHeight="20rem" />,
    );
    expect(out).toContain("sticky top-0");
    expect(out).toContain("max-height:20rem");
    expect(html(<Table caption="Runs" rows={[]} rowKey={() => "x"} columns={[]} />)).not.toContain("sticky");
  });

  it("PageHeader shows an eyebrow and can drop its divider", () => {
    const out = html(<PageHeader eyebrow="Workspace" title="Insights" description="What the evidence means." divider={false} />);
    expect(out).toContain("Workspace");
    expect(out).toContain("<h1");
    expect(out).not.toContain("border-b");
  });

  it("SectionHeader renders the requested heading level and action", () => {
    const out = html(<SectionHeader as="h3" id="s" title="Signals" description="Two found." action={<a href="#">All</a>} />);
    expect(out).toContain('<h3 id="s"');
    expect(out).toContain("Two found.");
    expect(out).toContain('<a href="#">All</a>');
  });

  it("Divider is a plain rule, or a labelled separator", () => {
    expect(html(<Divider />)).toContain("<hr");
    const labelled = html(<Divider label="Older" inset />);
    expect(labelled).toContain('role="separator"');
    expect(labelled).toContain('aria-label="Older"');
    expect(labelled).toContain("mx-4");
  });

  it("Disclosure is a button with aria-expanded over an inert collapsed region", () => {
    const closed = html(<Disclosure summary="More">Hidden body</Disclosure>);
    expect(closed).toContain('aria-expanded="false"');
    expect(closed).toContain('data-open="false"');
    expect(closed).toContain("inert");
    expect(html(<Disclosure summary="More" defaultOpen>Body</Disclosure>)).toContain('aria-expanded="true"');
  });

  it("CiteChip shows the source title in a tooltip rather than a native title", () => {
    const out = html(<CiteChip kind="evidence" index={2} label="Customer survey 2026" onOpen={() => undefined} />);
    expect(out).toContain('role="tooltip"');
    expect(out).toContain("Customer survey 2026");
    expect(out).not.toContain('title="');
  });
});

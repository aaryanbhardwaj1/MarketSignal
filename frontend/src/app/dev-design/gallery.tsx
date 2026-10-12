"use client";

import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { BarList } from "@/components/ui/bar-list";
import { Button, LinkButton } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardHeader } from "@/components/ui/card";
import { CiteChip, InferenceTag } from "@/components/ui/cite-chip";
import { CopyButton } from "@/components/ui/copy-button";
import { DevMetric } from "@/components/ui/dev-metric";
import { DevDetails, Disclosure } from "@/components/ui/disclosure";
import { Dialog, Drawer } from "@/components/ui/drawer";
import { EvidenceCard } from "@/components/ui/evidence-card";
import { ActiveFilters, FilterBar, FilterSelect } from "@/components/ui/filter-bar";
import { Checkbox, Field, Input, RadioGroup, Select, Textarea } from "@/components/ui/form-controls";
import { KeyValueList } from "@/components/ui/key-value";
import { LoadMore } from "@/components/ui/load-more";
import { MetricCard } from "@/components/ui/metric-card";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { ResultPanel } from "@/components/ui/result-panel";
import { SearchInput } from "@/components/ui/search-input";
import { Segmented } from "@/components/ui/segmented";
import { Section } from "@/components/ui/section";
import { CardGridSkeleton, EmptyState, ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Table, type Column } from "@/components/ui/table";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { Heading, Text } from "@/components/ui/typography";
import { opportunityStatus, sourceClass, terminationState } from "@/lib/labels";

const SWATCHES: Array<[string, string]> = [
  ["canvas", "--color-canvas"],
  ["surface", "--color-surface"],
  ["surface-muted", "--color-surface-muted"],
  ["surface-sunken", "--color-surface-sunken"],
  ["border", "--color-border"],
  ["border-strong", "--color-border-strong"],
  ["text", "--color-text"],
  ["text-secondary", "--color-text-secondary"],
  ["text-muted", "--color-text-muted"],
  ["accent", "--color-accent"],
  ["accent-subtle", "--color-accent-subtle"],
  ["success", "--color-success"],
  ["warn", "--color-warn"],
  ["danger", "--color-danger"],
  ["info", "--color-info"],
  ["cite-result", "--color-cite-result"],
  ["mark", "--color-mark"],
  ["chart-bar", "--color-chart-bar"],
];

const TYPE_SCALE: Array<[string, string]> = [
  ["text-xl", "24 / 32 page title"],
  ["text-lg", "20 / 28 large figure"],
  ["text-md", "16 / 24 section title"],
  ["text-base", "14 / 22 body"],
  ["text-sm", "13 / 20 secondary"],
  ["text-xs", "12 / 16 meta"],
];

type SampleRow = { id: string; title: string; cls: string; status: "ready" | "processing" | "failed"; passages: number; updated: string };
const ROWS: SampleRow[] = [
  { id: "1", title: "Sample source A", cls: "customer", status: "ready", passages: 128, updated: "Placeholder date" },
  { id: "2", title: "Sample source B", cls: "competitor", status: "processing", passages: 42, updated: "Placeholder date" },
  { id: "3", title: "Sample source C", cls: "market", status: "failed", passages: 0, updated: "Placeholder date" },
];
const STATUS = {
  ready: { tone: "success", label: "Ready" },
  processing: { tone: "info", label: "Processing" },
  failed: { tone: "danger", label: "Failed" },
} as const;
const COLUMNS: Column<SampleRow>[] = [
  { key: "title", header: "Source", cell: (r) => <span className="font-medium">{r.title}</span> },
  { key: "cls", header: "Class", cell: (r) => sourceClass(r.cls).label },
  { key: "status", header: "Status", cell: (r) => <StatusIndicator tone={STATUS[r.status].tone} label={STATUS[r.status].label} /> },
  { key: "passages", header: "Passages", cell: (r) => r.passages, align: "right" },
  { key: "updated", header: "Updated", cell: (r) => <span className="text-muted">{r.updated}</span> },
];

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-medium text-muted">{title}</p>
      {children}
    </div>
  );
}

function Grid({ cols = 3, top = false, children }: { cols?: 2 | 3 | 4; top?: boolean; children: ReactNode }) {
  const c = { 2: "md:grid-cols-2", 3: "md:grid-cols-3", 4: "md:grid-cols-2 lg:grid-cols-4" }[cols];
  return <div className={`grid gap-4 ${c} ${top ? "items-start" : ""}`}>{children}</div>;
}

/** `initialOverlay` (from `?open=drawer|dialog`) opens an overlay on load, for screenshots. */
export function Gallery({ initialOverlay }: { initialOverlay?: "drawer" | "dialog" }) {
  const [tab, setTab] = useState("overview");
  const [drawer, setDrawer] = useState(initialOverlay === "drawer");
  const [dialog, setDialog] = useState(initialOverlay === "dialog");
  const [mode, setMode] = useState("auto");
  const [cls, setCls] = useState("all");
  const [loading, setLoading] = useState(false);

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumb={[{ label: "Developer tools", href: "/dev-design" }]}
        title="Design gallery"
        description="Every design-system primitive and state, rendered with the production tokens. Development builds only."
        meta={<><span>Light theme</span><span aria-hidden>·</span><span>Tokens in styles/tokens.css</span></>}
        actions={<><Button variant="secondary" onClick={() => setDialog(true)}>Open dialog</Button><Button onClick={() => setDrawer(true)}>Open drawer</Button></>}
      />

      <div className="mt-6">
        <Callout tone="info" title="All content on this page is placeholder sample data">
          Labels and values exist only to show layout and states. They are not workspace data.
        </Callout>
      </div>

      <Section title="Tokens" description="Semantic colours, type scale and radii.">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {SWATCHES.map(([name, v]) => (
            <div key={name} className="overflow-hidden rounded-md border border-border bg-surface">
              <div className="h-10 border-b border-border" style={{ background: `var(${v})` }} />
              <p className="px-2 py-1.5 text-xs text-secondary">{name}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card>
            <ul className="flex flex-col gap-2">
              {TYPE_SCALE.map(([cls, note]) => (
                <li key={cls} className="flex items-baseline justify-between gap-4">
                  <span className={`${cls} text-primary`}>Growth signals</span>
                  <span className="text-xs text-muted">{note}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <div className="flex items-end gap-4">
              {["rounded-sm", "rounded-md", "rounded-lg", "rounded-full"].map((r) => (
                <div key={r} className="flex flex-col items-center gap-1.5">
                  <div className={`h-12 w-12 border border-border-strong bg-surface-muted ${r}`} />
                  <span className="text-xs text-muted">{r.replace("rounded-", "")}</span>
                </div>
              ))}
              <div className="ml-auto flex flex-col items-center gap-1.5">
                <div className="h-12 w-20 rounded-lg border border-border bg-surface shadow-overlay" />
                <span className="text-xs text-muted">overlay shadow</span>
              </div>
            </div>
          </Card>
        </div>
      </Section>

      <Section title="Typography">
        <Card>
          <Heading level={1}>Heading level 1</Heading>
          <Heading level={2} className="mt-3">Heading level 2</Heading>
          <Heading level={3} className="mt-3">Heading level 3</Heading>
          <Text className="mt-3">Default body text sits at 14px with a 22px line height for calm, dense reading across tables and answers.</Text>
          <Text tone="secondary" size="sm" className="mt-1">Secondary text at 13px.</Text>
          <Text tone="muted" size="xs" className="mt-1">Muted meta text at 12px.</Text>
        </Card>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-2">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button loading>Saving</Button>
          <Button disabled>Disabled</Button>
          <Button size="sm">Small</Button>
          <Button size="sm" variant="secondary">Small secondary</Button>
          <LinkButton href="/dev-design">Link button</LinkButton>
        </div>
      </Section>

      <Section title="Badges and status" description="Status always pairs colour with a word.">
        <Grid cols={2}>
          <Card>
            <Block title="Badge tones">
              <div className="flex flex-wrap gap-2">
                <Badge tone="success">Verified</Badge>
                <Badge tone="warn">Degraded</Badge>
                <Badge tone="danger">Withdrawn</Badge>
                <Badge tone="info">Running</Badge>
                <Badge tone="neutral">Cancelled</Badge>
                <Badge tone="accent">New</Badge>
                <Badge tone="neutral" size="md">Medium badge</Badge>
              </div>
            </Block>
          </Card>
          <Card>
            <Block title="Status indicators (from lib/labels)">
              <div className="flex flex-wrap gap-x-5 gap-y-2">
                {(["supported", "mixed_evidence", "emerging", "needs_research"] as const).map((s) => {
                  const l = opportunityStatus(s);
                  return <StatusIndicator key={s} tone={l.tone ?? "neutral"} label={l.label} />;
                })}
                {(["completed", "generation_unavailable", "error"] as const).map((s) => {
                  const l = terminationState(s);
                  return <StatusIndicator key={s} tone={l.tone ?? "neutral"} label={l.label} />;
                })}
              </div>
            </Block>
          </Card>
        </Grid>
      </Section>

      <Section title="Form controls">
        <Card>
          <div className="grid gap-5 md:grid-cols-2">
            <Field id="g-name" label="Name" hint="Shown in the sidebar.">
              <Input id="g-name" placeholder="Workspace name" />
            </Field>
            <Field id="g-err" label="Code" error="Use 3 to 12 capital letters.">
              <Input id="g-err" aria-invalid defaultValue="ab" />
            </Field>
            <Field id="g-sel" label="Source class">
              <Select id="g-sel" options={[{ value: "customer", label: "Customer research" }, { value: "market", label: "Market research" }]} />
            </Field>
            <Field id="g-search" label="Search">
              <SearchInput id="g-search-input" label="Search the evidence library" placeholder="Search the evidence library" onSubmit={() => undefined} />
            </Field>
            <Field id="g-ta" label="Question" className="md:col-span-2">
              <Textarea id="g-ta" rows={3} placeholder="Ask a question about this workspace" />
            </Field>
            <RadioGroup
              name="g-mode"
              legend="Answer mode"
              value={mode}
              onChange={setMode}
              orientation="horizontal"
              options={[{ value: "auto", label: "Automatic" }, { value: "standard", label: "Standard" }, { value: "research", label: "Research" }]}
            />
            <Segmented
              label="Answer mode (segmented)"
              visibleLabel="Mode"
              value={mode}
              onChange={setMode}
              options={[{ value: "auto", label: "Automatic" }, { value: "standard", label: "Standard" }, { value: "research", label: "Research" }]}
            />
            <Checkbox id="g-cb" label="Include archived sources" />
          </div>
        </Card>
      </Section>

      <Section title="Tabs">
        <Tabs label="Gallery sections" idPrefix="gal" value={tab} onChange={setTab} tabs={[{ id: "overview", label: "Overview" }, { id: "runs", label: "Runs", count: 24 }, { id: "tools", label: "Research steps" }]} />
        <TabPanel idPrefix="gal" id={tab}>
          <Text tone="secondary">Selected panel: {tab}. Use the arrow keys, Home and End to move between tabs.</Text>
        </TabPanel>
      </Section>

      <Section title="Filter bar">
        <Card>
          <FilterBar onReset={() => setCls("all")}>
            <FilterSelect id="g-f-class" label="Class" value={cls} onChange={setCls} options={[{ value: "all", label: "All classes" }, { value: "customer", label: "Customer research" }, { value: "competitor", label: "Competitor" }]} />
            <FilterSelect id="g-f-status" label="Status" value="any" onChange={() => undefined} options={[{ value: "any", label: "Any status" }]} />
          </FilterBar>
          <div className="mt-3">
            <ActiveFilters items={cls === "all" ? [{ label: "Updated this month", onRemove: () => undefined }] : [{ label: sourceClass(cls).label, onRemove: () => setCls("all") }]} />
          </div>
        </Card>
      </Section>

      <Section title="Cards and metrics">
        <Grid cols={4}>
          <MetricCard label="Sample metric" value="42" context="Placeholder context line" provenance="Placeholder provenance" />
          <MetricCard label="With unit" value="18.5" unit="%" tone="success" context="Tone dot plus label" />
          <MetricCard label="Linked metric" value="7" href="/dev-design" context="Whole card is a link" />
          <MetricCard label="Missing value" value={<span className="text-muted">Not available</span>} context="Never shown as zero" />
        </Grid>
        <div className="mt-4">
          <Grid cols={3}>
            <DevMetric label="Sample ratio" value={0.812} unit="ratio" ci={[0.77, 0.85]} n={120} source={{ path: "eval/sample.json", pointer: "/metrics/x" }} />
            <DevMetric label="Sample latency p50" value={1840} unit="ms" n={64} />
            <DevMetric label="Unmeasured" value={null} unit="percent" />
          </Grid>
        </div>
        <div className="mt-4">
          <Grid cols={2}>
            <Card padding="none">
              <CardHeader title="Card with header" meta="Header meta line" actions={<Button size="sm" variant="ghost">Action</Button>} />
              <div className="p-5">
                <KeyValueList columns={2} items={[{ label: "Owner", value: "Sample team" }, { label: "Version", value: "3" }, { label: "Class", value: "Customer research" }, { label: "Type", value: "PDF" }]} />
              </div>
            </Card>
            <Card interactive>
              <Text className="font-medium">Interactive card</Text>
              <Text tone="secondary" size="sm" className="mt-1">Hover changes the border only; cards never cast shadows.</Text>
            </Card>
          </Grid>
        </div>
      </Section>

      <Section title="Table">
        <Table caption="Sample sources" showCaption columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} onRowClick={() => setDrawer(true)} />
        <div className="mt-4">
          <Table caption="Empty table" columns={COLUMNS} rows={[]} rowKey={(r) => r.id} density="compact" empty="No sources match these filters." />
        </div>
      </Section>

      <Section title="Citations and evidence">
        <Card>
          <p className="max-w-reading text-base leading-7 text-primary">
            Sample sentence supported by an evidence passage
            <CiteChip kind="evidence" index={1} label="Sample source A" onOpen={() => setDrawer(true)} />. A second claim cites a computed figure
            <CiteChip kind="result" index={1} label="Sample computed result" onOpen={() => setDrawer(true)} />, and this one is the assistant&apos;s reading
            <InferenceTag />. Unverified and stale states:
            <CiteChip kind="evidence" index={2} label="Sample source B" state="unverified" onOpen={() => undefined} />
            <CiteChip kind="evidence" index={3} label="Sample source C" state="stale" onOpen={() => undefined} />.
          </p>
        </Card>
        <div className="mt-4">
          <Grid cols={2}>
            <EvidenceCard source={{ title: "Sample source A", type: "PDF", classLabel: "Customer research", version: 2 }} locator="Page 4" quote="Placeholder passage text that shows how a quoted evidence passage reads at body size with a quiet left rule." role="support" integrity="verified" onOpen={() => setDrawer(true)} />
            <EvidenceCard source={{ title: "Sample source B", type: "Presentation", classLabel: "Competitor", version: 1 }} locator="Slide 8" quote="Placeholder passage text for a contradicting passage from a source that has since been updated." role="contradict" integrity="stale" />
          </Grid>
        </div>
        <div className="mt-4">
          <Grid cols={2}>
            <ResultPanel title="Sample computed figure" value="64.2" unit="%" denominator={{ label: "Base", value: "Placeholder rows" }} filters={["Sample filter"]} groupBy={["Sample group"]} provenance={{ sourceTitle: "Sample dataset", sourceCode: "SAMPLE", version: 1, table: "responses" }} />
            <Card>
              <Block title="Bar list">
                <BarList ariaLabel="Sample distribution" items={[{ label: "Category one", value: 48, display: "48" }, { label: "Category two", value: 31, display: "31", emphasis: true }, { label: "Category three", value: 12, display: "12" }, { label: "Category four", value: 4, display: "4" }]} />
              </Block>
            </Card>
          </Grid>
        </div>
      </Section>

      <Section title="States">
        <Grid cols={2} top>
          <EmptyState title="No conversations yet" description="Ask a question to start a conversation. Saved answers appear here." action={<Button size="sm">Ask a question</Button>} />
          <ErrorState title="Could not load research runs" description="The service did not respond. Your data is safe." retry={() => undefined} devDetail="RUN_NOT_FOUND" />
          <Card>
            <LoadingRegion label="Loading sources" lines={4} />
          </Card>
          <Card>
            <Skeleton height="96px" />
          </Card>
        </Grid>
        <div className="mt-4">
          <CardGridSkeleton label="Loading summary cards" count={3} columns="md:grid-cols-3" />
        </div>
      </Section>

      <Section title="Callouts">
        <div className="flex flex-col gap-3">
          <Callout tone="info" title="Answers cite workspace evidence">Open any citation to read the passage.</Callout>
          <Callout tone="warn" title="Live model unavailable" action={<Button size="sm" variant="secondary">View saved answers</Button>}>Saved answers and evidence are still available.</Callout>
          <Callout tone="danger" title="This source has been withdrawn" />
          <Callout tone="neutral" title="Neutral note">Low-emphasis context for a page.</Callout>
        </div>
      </Section>

      <Section title="Disclosure, tooltip and utilities">
        <Grid cols={2}>
          <div className="flex flex-col gap-3">
            <Disclosure summary="Research details">
              <KeyValueList items={[{ label: "Mode", value: "Research" }, { label: "Research steps", value: "5" }]} />
              <div className="mt-3">
                <DevDetails data={{ handle: "SAMPLE/SOURCE@v1:P1", flags: [] }} />
              </div>
            </Disclosure>
            <Disclosure summary="Open by default" defaultOpen>
              <Text tone="secondary">Disclosures use native details and summary.</Text>
            </Disclosure>
          </div>
          <Card>
            <div className="flex flex-wrap items-center gap-4">
              <Tooltip content="Estimated from list prices">
                <button type="button" className="rounded-sm text-base text-accent-text underline decoration-dotted underline-offset-2">Hover or focus me</button>
              </Tooltip>
              <span className="flex items-center gap-1 text-sm text-muted">Sample id <CopyButton value="sample-id" /></span>
              <mark className="evidence-mark">highlighted span</mark>
            </div>
            <div className="mt-4 border-t border-border pt-2">
              <LoadMore hasMore loading={loading} onLoadMore={() => { setLoading(true); setTimeout(() => setLoading(false), 800); }} />
            </div>
          </Card>
        </Grid>
      </Section>

      <Drawer open={drawer} onClose={() => setDrawer(false)} title="Sample source A" subtitle="Customer research · PDF · Page 4" footer={<div className="flex justify-end"><Button variant="secondary" size="sm" onClick={() => setDrawer(false)}>Close</Button></div>}>
        <p className="text-base leading-7 text-primary">Placeholder passage with a <mark className="evidence-mark">highlighted span</mark> inside the surrounding context.</p>
        <div className="mt-4"><DevDetails data={{ handle: "SAMPLE/SOURCE@v1:P1" }} /></div>
      </Drawer>
      <Dialog open={dialog} onClose={() => setDialog(false)} title="Remove this filter set?" description="Saved filters for this page will be cleared." footer={<><Button variant="secondary" onClick={() => setDialog(false)}>Cancel</Button><Button variant="danger" onClick={() => setDialog(false)}>Remove</Button></>} />
    </PageContainer>
  );
}

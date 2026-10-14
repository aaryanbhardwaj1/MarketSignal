"use client";

import { Activity, ArrowRight, Download, FlaskConical, PanelLeft, Plus } from "lucide-react";
import { useState } from "react";
import { Sparkline } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import { Button, LinkButton } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { ClaimTag } from "@/components/ui/claim-tag";
import { Divider } from "@/components/ui/divider";
import { ActiveFilters, FilterBar, FilterSelect } from "@/components/ui/filter-bar";
import { Checkbox, Field, Input, RadioGroup, Select, Textarea } from "@/components/ui/form-controls";
import { MetricCard } from "@/components/ui/metric-card";
import { SearchInput } from "@/components/ui/search-input";
import { Segmented } from "@/components/ui/segmented";
import { Stat, StatRow } from "@/components/ui/stat";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { StatusPill } from "@/components/ui/status-pill";
import { Table, type Column } from "@/components/ui/table";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { Block, GallerySection, Grid, SampleNote } from "./gallery-parts";

type SampleRow = { id: string; title: string; cls: string; status: "ready" | "processing" | "failed"; passages: number; share: string };
const ROWS: SampleRow[] = [
  { id: "1", title: "Sample source A", cls: "Customer research", status: "ready", passages: 1284, share: "42.0%" },
  { id: "2", title: "Sample source B", cls: "Competitor material", status: "processing", passages: 42, share: "8.5%" },
  { id: "3", title: "Sample source C", cls: "Market report", status: "failed", passages: 0, share: "0.0%" },
  { id: "4", title: "Sample source D", cls: "Market report", status: "ready", passages: 310, share: "19.1%" },
  { id: "5", title: "Sample source E", cls: "Customer research", status: "ready", passages: 96, share: "6.2%" },
];
const STATUS = {
  ready: { tone: "success", label: "Ready" },
  processing: { tone: "info", label: "Processing" },
  failed: { tone: "danger", label: "Failed" },
} as const;
const COLUMNS: Column<SampleRow>[] = [
  { key: "title", header: "Source", cell: (r) => <span className="font-medium">{r.title}</span> },
  { key: "cls", header: "Class", cell: (r) => <span className="text-secondary">{r.cls}</span> },
  { key: "status", header: "Status", cell: (r) => <StatusIndicator tone={STATUS[r.status].tone} label={STATUS[r.status].label} /> },
  { key: "passages", header: "Passages", cell: (r) => r.passages.toLocaleString("en-US"), align: "right" },
  { key: "share", header: "Share", cell: (r) => r.share, align: "right" },
];

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "signals", label: "Signals", count: 12 },
  { id: "risks", label: "Risks and blockers", count: 3 },
];

export function ControlsSection() {
  const [tab, setTab] = useState("overview");
  const [mode, setMode] = useState<"auto" | "evidence" | "analytics">("auto");
  const [cls, setCls] = useState("all");
  const [query, setQuery] = useState("");
  return (
    <>
      <GallerySection id="buttons" title="Buttons" description="One primary action per view. Secondary is the hairline default; ghost and quiet sit in toolbars and inline.">
        <Grid cols={2}>
          <Block title="Variants (md)">
            <div className="flex flex-wrap items-center gap-2">
              <Button iconLeft={<Plus aria-hidden />}>Primary</Button>
              <Button variant="secondary" iconLeft={<Download aria-hidden />}>Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="quiet">Quiet</Button>
              <Button variant="danger">Danger</Button>
            </div>
          </Block>
          <Block title="Small, loading, disabled, link">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm">Primary</Button>
              <Button size="sm" variant="secondary">Secondary</Button>
              <Button size="sm" loading>Saving</Button>
              <Button size="sm" variant="secondary" disabled>Disabled</Button>
              <LinkButton size="sm" variant="quiet" href="/dev-design#buttons">
                View all <ArrowRight aria-hidden />
              </LinkButton>
            </div>
          </Block>
          <Block title="IconButton (md, active, sm)">
            <div className="flex flex-wrap items-center gap-2">
              <IconButton label="Telemetry" icon={<Activity aria-hidden />} />
              <IconButton label="RAG Evaluation" icon={<FlaskConical aria-hidden />} active />
              <IconButton label="Collapse sidebar" icon={<PanelLeft aria-hidden />} size="sm" />
            </div>
          </Block>
        </Grid>
      </GallerySection>

      <GallerySection id="labels" title="Badges, claim types and statuses" description="Exact product labels. Dashed outlines mark interpretation and forward-looking claims.">
        <Grid cols={3}>
          <Block title="ClaimTag (focus or hover the second row)">
            <div className="flex flex-wrap gap-2">
              <ClaimTag type="observed" />
              <ClaimTag type="derived" />
              <ClaimTag type="inference" />
              <ClaimTag type="hypothesis" />
              <ClaimTag type="forecast" />
            </div>
            <div className="flex flex-wrap gap-2">
              <ClaimTag type="observed" size="sm" explain />
              <ClaimTag type="inference" size="sm" explain />
              <ClaimTag type="forecast" size="sm" explain />
            </div>
          </Block>
          <Block title="StatusPill">
            <div className="flex flex-wrap gap-2">
              <StatusPill status="strong_evidence" />
              <StatusPill status="supported" />
              <StatusPill status="emerging" />
              <StatusPill status="mixed_evidence" />
              <StatusPill status="needs_validation" />
            </div>
          </Block>
          <Block title="Badge and StatusIndicator">
            <div className="flex flex-wrap gap-2">
              <Badge tone="success">Verified</Badge>
              <Badge tone="warn">Stale</Badge>
              <Badge tone="danger">Failed</Badge>
              <Badge tone="info">Running</Badge>
              <Badge>Neutral</Badge>
              <Badge tone="accent" size="md">Accent</Badge>
            </div>
            <div className="flex flex-wrap gap-4">
              <StatusIndicator tone="success" label="Ready" detail="2 min ago" />
              <StatusIndicator tone="warn" label="Degraded" />
            </div>
          </Block>
        </Grid>
      </GallerySection>

      <GallerySection id="stats" title="Stats" description="Figures without boxes: hierarchy, whitespace and hairlines. MetricCard when a figure needs its provenance.">
        <SampleNote />
        <div className="mt-4">
          <StatRow>
            <Stat size="lg" label="Sample hero figure" value="1,284" sub="sample records" />
            <Stat label="Sample rate" value="34%" delta={{ label: "+4 pts", direction: "up", sentiment: "positive" }} sub="vs. sample prior period" />
            <Stat label="Sample trend" value="112" trend={<Sparkline ariaLabel="Sample trend" values={[4, 6, 5, 8, 9, 11]} emphasis />} />
            <Stat size="sm" tone="warn" label="Sample warning" value="3" sub="sources stale" />
          </StatRow>
        </div>
        <Divider className="my-6" label="MetricCard" />
        <Grid cols={3}>
          <MetricCard label="Sample share" value="42.0" unit="%" context="of sample respondents" provenance="From Sample source A · Version 1" />
          <MetricCard label="Sample count" value="610" tone="success" context="sample records" href="/dev-design#stats" />
        </Grid>
      </GallerySection>

      <GallerySection id="forms" title="Forms and filters" description="One control height, accent focus ring, plain-language hints and errors.">
        <Grid cols={3}>
          <Block title="Field, input, select, textarea">
            <Field id="g-name" label="Engagement name" hint="Shown to everyone in this workspace.">
              <Input id="g-name" placeholder="Sample engagement" aria-describedby="g-name-hint" />
            </Field>
            <Field id="g-bad" label="Budget" error="Enter a number, for example 1200.">
              <Input id="g-bad" defaultValue="twelve" aria-invalid aria-describedby="g-bad-error" />
            </Field>
            <Field id="g-sel" label="Region">
              <Select id="g-sel" options={[{ value: "na", label: "North America" }, { value: "eu", label: "Europe" }]} />
            </Field>
            <Field id="g-notes" label="Notes">
              <Textarea id="g-notes" placeholder="Optional" />
            </Field>
          </Block>
          <Block title="Search, checkbox, radio">
            <SearchInput id="g-search" label="Search sources" placeholder="Search sample sources" onSubmit={setQuery} />
            {query && <p className="text-xs text-muted">Searched for “{query}”</p>}
            <Checkbox id="g-check" label="Only verified sources" defaultChecked />
            <RadioGroup
              name="g-radio"
              legend="Answer depth"
              value="brief"
              onChange={() => undefined}
              options={[
                { value: "brief", label: "Brief", description: "A short answer with citations." },
                { value: "full", label: "Full", description: "Detailed answer with analysis." },
              ]}
            />
          </Block>
          <Block title="FilterBar and active filters">
            <FilterBar onReset={() => setCls("all")}>
              <FilterSelect
                id="g-cls"
                label="Class"
                value={cls}
                onChange={setCls}
                options={[{ value: "all", label: "All classes" }, { value: "customer", label: "Customer research" }]}
              />
            </FilterBar>
            <ActiveFilters items={cls === "all" ? [] : [{ label: "Customer research", onRemove: () => setCls("all") }]} />
          </Block>
        </Grid>
      </GallerySection>

      <GallerySection id="navigation" title="Tabs and segmented" description="Underline tabs slide between sections; segmented controls switch a mode in place.">
        <Grid cols={2}>
          <Block title="Tabs">
            <Tabs label="Sample sections" tabs={TABS} value={tab} onChange={setTab} idPrefix="g-tabs" />
            <TabPanel idPrefix="g-tabs" id={tab}>
              <p className="text-sm text-secondary">Panel for {TABS.find((t) => t.id === tab)?.label}.</p>
            </TabPanel>
          </Block>
          <Block title="Segmented">
            <Segmented
              label="Answer mode"
              value={mode}
              onChange={setMode}
              options={[
                { value: "auto", label: "Auto" },
                { value: "evidence", label: "Evidence" },
                { value: "analytics", label: "Analytics" },
              ]}
            />
            <Segmented label="Disabled" value="auto" onChange={() => undefined} disabled options={[{ value: "auto", label: "Auto" }, { value: "off", label: "Off" }]} />
          </Block>
        </Grid>
      </GallerySection>

      <GallerySection id="tables" title="Tables" description="Quiet header, row hover, right-aligned tabular numbers. Sticky header inside its own scroll frame.">
        <Grid cols={2}>
          <Block title="Comfortable, clickable rows">
            <Table caption="Sample sources" columns={COLUMNS} rows={ROWS.slice(0, 3)} rowKey={(r) => r.id} onRowClick={() => undefined} />
          </Block>
          <Block title="Compact, sticky header, empty">
            <Table caption="Sample sources, compact" columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} density="compact" stickyHeader maxHeight="9rem" />
            <Table caption="No sample rows" columns={COLUMNS} rows={[]} rowKey={(r) => r.id} density="compact" empty="No sources match these filters." />
          </Block>
        </Grid>
      </GallerySection>
    </>
  );
}

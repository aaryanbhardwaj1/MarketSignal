"use client";

import { FileSearch, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardHeader } from "@/components/ui/card";
import { CiteChip, InferenceTag } from "@/components/ui/cite-chip";
import { ClaimTag } from "@/components/ui/claim-tag";
import { CopyButton } from "@/components/ui/copy-button";
import { DevDetails, Disclosure } from "@/components/ui/disclosure";
import { Divider } from "@/components/ui/divider";
import { EvidenceCard } from "@/components/ui/evidence-card";
import { KeyValueList } from "@/components/ui/key-value";
import { NotRun } from "@/components/ui/not-run";
import { ResultPanel } from "@/components/ui/result-panel";
import { CardGridSkeleton, EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { Tooltip } from "@/components/ui/tooltip";
import { Block, GallerySection, Grid } from "./gallery-parts";

const noop = () => undefined;

export function ContentSection({ onOpenDrawer, onOpenDialog }: { onOpenDrawer: () => void; onOpenDialog: () => void }) {
  return (
    <>
      <GallerySection id="citations" title="Citations and evidence" description="Numbered citation pills show the source on hover or focus and open the evidence drawer.">
        <Grid cols={2}>
          <Block title="Inline citations in an answer">
            <p className="max-w-reading text-base leading-relaxed text-primary">
              Sample respondents in segment A report the highest repeat intent
              <CiteChip kind="evidence" index={1} label="Sample source A, page 4" onOpen={onOpenDrawer} />
              <CiteChip kind="evidence" index={2} label="Sample source B, row 43" state="stale" onOpen={onOpenDrawer} />, while the
              computed share is 46%
              <CiteChip kind="result" index={1} label="Share of respondents by segment" onOpen={onOpenDrawer} />. This likely reflects
              a loyalty effect <InferenceTag />.
            </p>
            <div className="flex flex-wrap items-center gap-2 text-sm text-secondary">
              <ClaimTag type="hypothesis" /> Segment A would respond to a sample bundle offer.
            </div>
          </Block>
          <Block title="EvidenceCard">
            <EvidenceCard
              source={{ title: "Sample source A", type: "PDF", classLabel: "Customer research" }}
              locator="page:4"
              quote="Placeholder passage: respondents in the sample segment describe returning for the same product line."
              role="support"
              onOpen={onOpenDrawer}
            />
            <EvidenceCard
              source={{ title: "Sample source B", type: "PDF", classLabel: "Market report" }}
              locator="page:12"
              quote="Placeholder passage that contradicts the claim above."
              role="contradict"
              integrity="stale"
            />
          </Block>
          <Block title="ResultPanel (computed)">
            <ResultPanel
              title="Sample share of respondents in segment A"
              value="46.0"
              unit="%"
              denominator={{ label: "Base", value: "276 of 600 sample records" }}
              filters={["Region is North America"]}
              provenance={{ sourceTitle: "Sample dataset", sourceCode: "SAMPLE", version: 1, table: "Survey_Responses" }}
            />
          </Block>
          <Block title="Card (default, raised, plain) and key values">
            <Card padding="none">
              <CardHeader title="Sample card" meta="Hairline, no heavy chrome" actions={<Button size="sm" variant="ghost">Edit</Button>} />
              <div className="p-5">
                <KeyValueList columns={2} items={[{ label: "Owner", value: "Sample team" }, { label: "Updated", value: "Placeholder date" }]} />
              </div>
            </Card>
            <Card variant="raised" padding="sm">
              <p className="text-sm text-secondary">Raised: the one element that should lift.</p>
            </Card>
            <Card variant="plain" as="section">
              <p className="text-sm text-secondary">Plain: just a section, separated by whitespace.</p>
            </Card>
          </Block>
        </Grid>
      </GallerySection>

      <GallerySection id="states" title="States" description="Teach the next step when empty; stay calm on failure; say plainly what was not measured.">
        <Grid cols={2}>
          <Block title="EmptyState (with icon) and compact">
            <EmptyState
              icon={MessageSquare}
              title="No conversations yet"
              description="Ask a question about your sources and the answer will cite every passage it uses."
              action={<Button size="sm">New chat</Button>}
            />
            <EmptyState icon={FileSearch} size="sm" title="No sources match" description="Try a broader search or clear the filters." />
          </Block>
          <Block title="NotRun, ErrorState">
            <NotRun title="Evaluation not yet run" reason="The held-out split has not been scored. Nothing is estimated in its place." detail="Run it from the evaluation CLI." />
            <NotRun reason="Latency was not measured for this run." />
            <ErrorState title="Could not load runs" description="The server did not respond. Your saved work is safe." retry={noop} devDetail="SAMPLE_CODE" />
          </Block>
          <Block title="Skeleton (shimmer)">
            <Skeleton lines={3} />
            <Skeleton height="4rem" />
          </Block>
          <Block title="CardGridSkeleton">
            <CardGridSkeleton label="Loading sample cards" count={2} lines={2} columns="sm:grid-cols-2" gap="sm" padding="sm" />
          </Block>
        </Grid>
      </GallerySection>

      <GallerySection id="callouts" title="Callouts and disclosure" description="Inline notices name their tone for assistive tech. Disclosures animate open; technical detail stays collapsed.">
        <Grid cols={2}>
          <Block title="Callout tones">
            <Callout tone="info" title="Live model unavailable">Saved research, evidence and analytics still work.</Callout>
            <Callout tone="warn" title="Two sources were updated">Citations to the old versions are marked.</Callout>
            <Callout tone="danger" title="This run failed" action={<Button size="sm" variant="secondary">Retry</Button>} />
            <Callout tone="neutral" title="Forecasts are labelled">They are shown only when a source states the projection.</Callout>
          </Block>
          <Block title="Disclosure, DevDetails, tooltip, divider">
            <Disclosure summary="Why this is a hypothesis">
              <p className="text-sm text-secondary">No source states it directly; it is a proposition to test with sample research.</p>
            </Disclosure>
            <Disclosure summary="Open by default" defaultOpen variant="plain">
              <p className="text-sm text-secondary">Plain variant beside technical details.</p>
            </Disclosure>
            <DevDetails data={{ handle: "SAMPLE/SOURCE@v1:P1", flags: [] }} />
            <Divider label="Older" />
            <div className="flex flex-wrap items-center gap-4">
              <Tooltip content="Estimated from sample list prices">
                <button type="button" className="rounded-sm text-sm text-accent-text underline decoration-dotted underline-offset-2">
                  Hover or focus me
                </button>
              </Tooltip>
              <span className="flex items-center gap-1 text-sm text-muted">
                Sample id <CopyButton value="sample-id" />
              </span>
              <mark className="evidence-mark">highlighted span</mark>
            </div>
          </Block>
        </Grid>
      </GallerySection>

      <GallerySection id="overlays" title="Drawer and dialog" description="Native dialog: focus trap, Esc to close, focus returns to the opener. The drawer slides in from the right.">
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={onOpenDrawer}>Open drawer</Button>
          <Button variant="secondary" onClick={onOpenDialog}>Open dialog</Button>
        </div>
      </GallerySection>
    </>
  );
}

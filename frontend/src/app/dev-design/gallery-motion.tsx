"use client";

import { useState } from "react";
import { PulseNode, ScanLine, SignalLoader, StageProgress, type Stage } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Block, GallerySection, Grid } from "./gallery-parts";

const STAGES: Stage[] = [
  { id: "plan", label: "Plan the question", state: "done", timing: "0.4 s" },
  { id: "retrieve", label: "Search the evidence", detail: "Reading sample sources", state: "active" },
  { id: "analyse", label: "Run the analysis", state: "pending" },
  { id: "deck", label: "Draft a deck", state: "skipped" },
  { id: "verify", label: "Verify citations", state: "failed", detail: "Sample failure state" },
];

export function MotionSection() {
  const [scanning, setScanning] = useState(true);
  return (
    <GallerySection id="motion" title="Motion" description="Quiet and purposeful: 120 / 200 / 320 ms, standard easing. Reduced motion falls back to opacity or nothing.">
      <Grid cols={3}>
        <Block title="SignalLoader sm / md / lg">
          <div className="flex items-end gap-6">
            <SignalLoader size="sm" label="Loading sample" />
            <SignalLoader size="md" label="Loading sample" />
            <SignalLoader size="lg" label="Loading sample" showLabel />
          </div>
        </Block>
        <Block title="ScanLine">
          <Card padding="sm" className="relative overflow-hidden">
            <ScanLine active={scanning} />
            <p className="mt-3 text-sm text-secondary">{scanning ? "Scanning sample sources" : "Scan stopped"}</p>
          </Card>
          <div>
            <Button size="sm" variant="secondary" onClick={() => setScanning((v) => !v)}>
              {scanning ? "Stop" : "Start"} scan
            </Button>
          </div>
        </Block>
        <Block title="PulseNode tones (active, then idle)">
          <div className="flex items-center gap-4">
            <PulseNode tone="accent" active />
            <PulseNode tone="success" active />
            <PulseNode tone="warn" active size="sm" />
            <PulseNode tone="danger" />
            <PulseNode tone="neutral" />
          </div>
        </Block>
      </Grid>
      <div className="mt-8 grid gap-8 lg:grid-cols-[18rem_1fr]">
        <Block title="StageProgress vertical (mixed states)">
          <StageProgress stages={STAGES} orientation="vertical" label="Sample research progress" />
        </Block>
        <Block title="StageProgress horizontal">
          <StageProgress stages={STAGES} orientation="horizontal" label="Sample research progress" />
        </Block>
      </div>
    </GallerySection>
  );
}

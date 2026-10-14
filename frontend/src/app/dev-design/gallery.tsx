"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ClaimTag } from "@/components/ui/claim-tag";
import { DevDetails } from "@/components/ui/disclosure";
import { Dialog, Drawer } from "@/components/ui/drawer";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { ChartsSection } from "./gallery-charts";
import { ContentSection } from "./gallery-content";
import { ControlsSection } from "./gallery-controls";
import { FoundationsSection } from "./gallery-foundations";
import { MotionSection } from "./gallery-motion";

const NAV: Array<[string, string]> = [
  ["tokens", "Tokens"],
  ["type", "Type"],
  ["brand", "Brand"],
  ["buttons", "Buttons"],
  ["labels", "Labels"],
  ["stats", "Stats"],
  ["forms", "Forms"],
  ["navigation", "Tabs"],
  ["tables", "Tables"],
  ["citations", "Citations"],
  ["states", "States"],
  ["callouts", "Callouts"],
  ["overlays", "Overlays"],
  ["charts", "Charts"],
  ["motion", "Motion"],
];

/** `initialOverlay` (from `?open=drawer|dialog`) opens an overlay on load, for screenshots. */
export function Gallery({ initialOverlay }: { initialOverlay?: "drawer" | "dialog" }) {
  const [drawer, setDrawer] = useState(initialOverlay === "drawer");
  const [dialog, setDialog] = useState(initialOverlay === "dialog");

  return (
    <PageContainer width="wide">
      <PageHeader
        eyebrow="Developer tools"
        title="Design gallery"
        description="Every primitive, chart and motion component in one place. All figures here are sample data."
      />
      <nav aria-label="Gallery sections" className="sticky top-0 z-20 -mx-1 mt-4 mb-8 flex flex-wrap gap-1 bg-canvas/95 py-2">
        {NAV.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="rounded-md px-2 py-1 text-sm text-secondary transition-colors duration-(--duration-fast) ease-standard hover:bg-surface-muted hover:text-primary"
          >
            {label}
          </a>
        ))}
      </nav>
      <div className="flex flex-col gap-12 pb-24">
        <FoundationsSection />
        <ControlsSection />
        <ContentSection onOpenDrawer={() => setDrawer(true)} onOpenDialog={() => setDialog(true)} />
        <ChartsSection />
        <MotionSection />
      </div>

      <Drawer
        open={drawer}
        onClose={() => setDrawer(false)}
        title="Sample source A"
        subtitle="Customer research · PDF · Page 4"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setDrawer(false)}>Close</Button>
            <Button variant="secondary" size="sm">View source</Button>
          </>
        }
      >
        <div className="flex items-center gap-2">
          <ClaimTag type="observed" size="sm" />
          <span className="text-xs text-muted">Passage 1 of 3</span>
        </div>
        <p className="mt-3 text-base leading-7 text-primary">
          Placeholder passage with a <mark className="evidence-mark">highlighted span</mark> inside the surrounding context.
        </p>
        <div className="mt-4">
          <DevDetails data={{ handle: "SAMPLE/SOURCE@v1:P1" }} />
        </div>
      </Drawer>
      <Dialog
        open={dialog}
        onClose={() => setDialog(false)}
        title="Remove this filter set?"
        description="Saved filters for this page will be cleared."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(false)}>Cancel</Button>
            <Button variant="danger" onClick={() => setDialog(false)}>Remove</Button>
          </>
        }
      />
    </PageContainer>
  );
}

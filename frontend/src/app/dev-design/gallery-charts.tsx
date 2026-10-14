import {
  Distribution,
  EvidenceBalance,
  GroupedBarChart,
  HBarChart,
  LineChart,
  Sparkline,
  StackedBar,
  StageBreakdown,
} from "@/components/charts";
import { Card } from "@/components/ui/card";
import { Block, GallerySection, Grid, SampleNote } from "./gallery-parts";

const pct = (v: number) => `${Math.round(v)}%`;
const ms = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);

const LATENCIES = [420, 460, 510, 530, 560, 590, 610, 640, 700, 720, 760, 810, 880, 940, 1020, 1150, 1380, 1720, 2100, 2650];

/** Every chart from components/charts, with clearly labelled sample data. */
export function ChartsSection() {
  return (
    <GallerySection id="charts" title="Charts" description="Hand-rolled accessible SVG: figure, caption, value labels, hidden data table. Emphasis colour only where it matters.">
      <SampleNote />
      <div className="mt-5">
        <Grid cols={2}>
          <Block title="HBarChart (with interval and reference)">
            <HBarChart
              ariaLabel="Sample share of respondents by segment"
              title="Share of respondents by segment"
              caption="Sample data."
              format={pct}
              reference={{ value: 30, label: "Sample average" }}
              data={[
                { label: "Segment A", value: 46, low: 41, high: 51, emphasis: true },
                { label: "Segment B", value: 31, low: 27, high: 35 },
                { label: "Segment C", value: 18, low: 14, high: 22 },
                { label: "Segment D", value: 5 },
              ]}
            />
          </Block>
          <Block title="GroupedBarChart">
            <GroupedBarChart
              ariaLabel="Sample units by quarter and channel"
              title="Units by quarter and channel"
              caption="Sample data."
              categories={["Q1", "Q2", "Q3", "Q4"]}
              series={[
                { name: "Direct", values: [120, 140, 165, 180] },
                { name: "Partner", values: [90, 95, 88, 110] },
              ]}
            />
          </Block>
          <Block title="LineChart (with band; hover or arrow keys)">
            <LineChart
              ariaLabel="Sample monthly index with range"
              title="Monthly index"
              caption="Sample data."
              x={["Jan", "Feb", "Mar", "Apr", "May", "Jun"]}
              series={[{ name: "Index", values: [100, 104, 103, 109, 115, 118] }]}
              band={{ low: [96, 99, 98, 103, 108, 110], high: [104, 109, 108, 115, 122, 126], label: "Sample range" }}
            />
          </Block>
          <Block title="Distribution (histogram and strip, p50 / p95)">
            <Distribution ariaLabel="Sample latency distribution" title="Latency" caption="Sample data." values={LATENCIES} format={ms} />
            <Distribution ariaLabel="Sample latency strip" variant="strip" values={LATENCIES} format={ms} />
          </Block>
          <Block title="StackedBar">
            <StackedBar
              ariaLabel="Sample source mix"
              title="Source mix"
              caption="Sample data."
              segments={[
                { label: "Customer research", value: 48 },
                { label: "Market reports", value: 32 },
                { label: "Competitor material", value: 20 },
              ]}
            />
          </Block>
          <Block title="EvidenceBalance">
            <EvidenceBalance supporting={7} contradicting={2} neutral={1} caption="Sample passages." />
          </Block>
          <Block title="StageBreakdown">
            <StageBreakdown
              ariaLabel="Sample run stage timings"
              title="Run stages"
              caption="Sample data."
              format={ms}
              stages={[
                { label: "Plan", duration: 380 },
                { label: "Retrieve", duration: 1240, emphasis: true },
                { label: "Analyse", duration: 610 },
                { label: "Write", duration: 2050 },
                { label: "Verify", duration: 420 },
              ]}
            />
          </Block>
          <Block title="Sparkline">
            <Card padding="sm">
              <div className="flex items-center gap-6">
                <Sparkline ariaLabel="Sample weekly trend" values={[4, 6, 5, 8, 9, 7, 11, 12]} emphasis />
                <Sparkline ariaLabel="Sample flat trend" values={[6, 6, 7, 6, 5, 6, 6, 7]} />
              </div>
            </Card>
          </Block>
          <Block title="Empty (no data, honest state)">
            <HBarChart ariaLabel="Sample chart with no data" title="Share by segment" data={[]} />
          </Block>
        </Grid>
      </div>
    </GallerySection>
  );
}

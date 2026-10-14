"use client";

import { Badge } from "@/components/ui/badge";
import { NotRun } from "@/components/ui/not-run";
import { Section } from "@/components/ui/section";
import type { EvalCatalog, RagasCaveat, RagasMetricDefinition, RagasSection } from "@/lib/api/contracts";
import { RAGAS_FRAMING, RAGAS_LLM_COMMAND, notRunReason, splitFamilies } from "@/lib/views/ragas";
import { useCatalogContext } from "../catalog-context";
import { RagasItems } from "./ragas-items";
import { RagasRunBlock } from "./ragas-run-block";

/** Caveats that get their own place in the panel; the rest are listed at the end. */
const PLACED_CAVEATS = new Set(["ragas-heuristics-not-truth", "ragas-llm-metrics-not-run", "ragas-offline-persisted-outputs"]);

function ProvenanceLine({ section }: { section: RagasSection }) {
  const parts = [
    `ragas ${section.ragas_version}`,
    section.telemetry_disabled ? "telemetry disabled" : "telemetry not disabled",
    "computed offline on persisted outputs",
    "no model calls",
  ];
  return (
    <p className="text-sm text-muted">
      {parts.map((p, i) => (
        <span key={p} className={i === 0 ? "font-mono" : undefined}>
          {i > 0 && <span aria-hidden> · </span>}
          {p}
        </span>
      ))}
    </p>
  );
}

function FamilyTitle({ title, tag, tone }: { title: string; tag: string; tone: "info" | "neutral" }) {
  return (
    <span className="flex flex-wrap items-center gap-2">
      {title}
      <Badge tone={tone}>{tag}</Badge>
    </span>
  );
}

function ModelJudged({ section, defs }: { section: RagasSection; defs: RagasMetricDefinition[] }) {
  return (
    <div className="flex flex-col gap-3">
      <ul className="grid gap-3 md:grid-cols-2">
        {defs.map((d) => (
          <li key={d.key} className="flex flex-col gap-2" data-model-judged={d.key}>
            <p className="text-sm font-medium text-primary">{d.label}</p>
            <p className="text-xs text-muted">{d.what_it_measures}</p>
            <NotRun reason={notRunReason(section, d)} />
          </li>
        ))}
      </ul>
      <div>
        <p className="text-sm text-secondary">
          These metrics are wired but call a judge model. They would run with the command below, which this demo does not
          execute.
        </p>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-md border border-border bg-sunken px-3 py-2 font-mono text-xs text-muted">
          <code>{RAGAS_LLM_COMMAND}</code>
        </pre>
      </div>
    </div>
  );
}

function OtherCaveats({ caveats }: { caveats: RagasCaveat[] }) {
  if (caveats.length === 0) return null;
  return (
    <Section title="Caveats">
      <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm text-secondary">
        {caveats.map((c) => (
          <li key={c.id}>{c.text}</li>
        ))}
      </ul>
    </Section>
  );
}

function caveatText(section: RagasSection, id: string): string | null {
  return section.caveats.find((c) => c.id === id)?.text ?? null;
}

/**
 * RAG Evaluation, RAGAS tab: offline heuristics beside the deterministic metrics, never instead of them.
 * `ws` is accepted for parity with the other tabs; nothing here links out of the panel.
 */
export function RagasPanel({ catalog: given }: { catalog?: EvalCatalog; ws?: string } = {}) {
  const fromContext = useCatalogContext();
  const catalog = given ?? fromContext;
  const section = catalog?.ragas;

  if (!catalog || !section) {
    return (
      <div data-testid="ragas-panel">
        <NotRun
          title="RAGAS not yet run"
          reason="This evaluation catalog has no RAGAS results. The deterministic metrics on the other tabs are unaffected."
        />
      </div>
    );
  }

  const { computed, modelJudged } = splitFamilies(section);
  const offline = caveatText(section, "ragas-offline-persisted-outputs");
  const notRun = caveatText(section, "ragas-llm-metrics-not-run");
  const remaining = section.caveats.filter((c) => !PLACED_CAVEATS.has(c.id) && c.metrics.length === 0);

  return (
    <div data-testid="ragas-panel">
      <header className="flex flex-col gap-1.5">
        <p className="text-base text-primary">{RAGAS_FRAMING}</p>
        <ProvenanceLine section={section} />
        {caveatText(section, "ragas-heuristics-not-truth") && (
          <p className="text-sm text-muted">{caveatText(section, "ragas-heuristics-not-truth")}</p>
        )}
      </header>

      <Section
        title={<FamilyTitle title="Computed offline" tag="No model" tone="info" />}
        description={offline ?? "Computed on persisted outputs and the committed gold datasets."}
      >
        <div className="flex flex-col gap-10">
          {section.runs.map((run) => (
            <RagasRunBlock key={run.id} run={run} defs={computed} caveats={section.caveats} catalog={catalog} />
          ))}
        </div>
      </Section>

      <Section title={<FamilyTitle title="Model-judged" tag="Not yet run" tone="neutral" />} description={notRun ?? undefined}>
        <ModelJudged section={section} defs={modelJudged} />
      </Section>

      <Section
        title="Item-level scores"
        description="Every scored item with its offline scores. Sort by a metric to bring outliers to the top; select a row for the full score list."
      >
        <RagasItems runs={section.runs} defs={computed} />
      </Section>

      <OtherCaveats caveats={remaining} />
    </div>
  );
}

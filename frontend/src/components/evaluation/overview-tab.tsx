import type { EvalCatalog } from "@/lib/api/contracts";
import { Section } from "@/components/ui/section";
import { allProvenance } from "@/lib/eval-view";
import { Caveats, ProvenanceTable } from "./caveats";
import { EvalStat } from "./metric-bits";

export const OVERVIEW_INTRO =
  "MarketSignal evaluates retrieval, grounding, citation integrity and research behavior against versioned datasets with known expected evidence.";

export function OverviewTab({ catalog }: { catalog: EvalCatalog }) {
  return (
    <div>
      <p className="max-w-reading text-base text-secondary">
        {OVERVIEW_INTRO} Each figure on these pages is read from a committed evaluation artifact and links back to
        the file, JSON pointer and commit it came from. Failed cases are kept and can be reviewed under Failure
        analysis.
      </p>

      <div className="mt-6">
        <Caveats caveats={catalog.caveats} />
      </div>

      <Section title="Headline results" description="Point estimates with 95% confidence intervals and sample sizes where recorded.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {catalog.overview.headline.map((m) => (
            <EvalStat key={m.id} metric={m} />
          ))}
        </div>
      </Section>

      <Section title="Evaluation phases" description="Phases in the order they were built; each was measured against its own versioned dataset.">
        <ol className="grid gap-3 md:grid-cols-2">
          {catalog.overview.phases.map((p, i) => (
            <li key={p.id} className="flex gap-3 rounded-lg border border-border bg-surface p-4">
              <span
                aria-hidden
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border-strong text-xs font-semibold tabular-nums text-secondary"
              >
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="text-base font-semibold text-primary">{p.title}</p>
                <p className="mt-0.5 text-sm text-secondary">{p.summary}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        title="Datasets and runs"
        description="Dataset, split, timestamp, configuration and commit for each measured run."
      >
        <ProvenanceTable rows={allProvenance(catalog)} caption="Provenance of each evaluation run" />
      </Section>
    </div>
  );
}

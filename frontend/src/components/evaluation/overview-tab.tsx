import type { EvalCatalog } from "@/lib/api/contracts";
import { Card } from "@/components/ui/card";
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

      <Section title="Headline results" description="Point estimates with 95% confidence intervals and sample sizes where recorded.">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {catalog.overview.headline.map((m) => (
            <EvalStat key={m.id} metric={m} />
          ))}
        </div>
      </Section>

      <div className="mt-6">
        <Caveats caveats={catalog.caveats} />
      </div>

      <Section title="Evaluation phases" description="Phases in the order they were built; each was measured against its own versioned dataset.">
        <ol className="grid gap-3 md:grid-cols-2">
          {catalog.overview.phases.map((p) => (
            <Card key={p.id} as="li" padding="sm" className="min-w-0">
              <p className="text-base font-semibold text-primary">{p.title}</p>
              <p className="mt-0.5 text-sm text-secondary">{p.summary}</p>
            </Card>
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

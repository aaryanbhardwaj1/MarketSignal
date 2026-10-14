import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/ui/section";
import type { EvalCatalog } from "@/lib/api/contracts";
import { DECISION_OUTCOME } from "@/lib/eval-view";
import { Caveats } from "./caveats";
import { headlineStory } from "./dashboard/derive";
import { StoryCards } from "./dashboard/story-cards";
import { MetricCell } from "./metric-bits";

export const OVERVIEW_INTRO =
  "Each figure on these pages is read from a committed evaluation artifact and links back to the file, pointer and commit it came from.";

/** Phase timeline; Phase 2 carries the retrieval decisions it produced. */
function DecisionTimeline({ catalog }: { catalog: EvalCatalog }) {
  const decisions = catalog.retrieval.decisions;
  return (
    <ol className="relative flex flex-col gap-5 border-l border-border pl-5">
      {catalog.overview.phases.map((p) => (
        <li key={p.id} className="relative">
          <span aria-hidden className="absolute -left-[1.4rem] top-1.5 size-2 rounded-full border border-border-strong bg-surface" />
          <p className="text-base font-semibold text-primary">{p.title}</p>
          <p className="mt-0.5 max-w-reading text-sm text-secondary">{p.summary}</p>
          {p.id === "retrieval" && decisions.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1.5">
              {decisions.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge tone={DECISION_OUTCOME[d.outcome].tone}>{DECISION_OUTCOME[d.outcome].label}</Badge>
                  <span className="text-primary">{d.title}</span>
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

export function OverviewTab({ catalog, ws }: { catalog: EvalCatalog; ws?: string }) {
  const cards = headlineStory(catalog);
  return (
    <div>
      <p className="max-w-reading text-sm text-secondary">{OVERVIEW_INTRO}</p>

      {cards.length > 0 && (
        <Section title="What the measurements decided" description="Point estimates with 95% confidence intervals and sample sizes where recorded.">
          <StoryCards cards={cards} ws={ws} />
        </Section>
      )}

      {catalog.overview.headline.length > 0 && (
        <Section title="Headline figures" description="As listed in the catalog's overview.">
          <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
            {catalog.overview.headline.map((m) => (
              <div key={m.id} className="flex items-start justify-between gap-4 border-b border-border pb-2">
                <dt className="text-sm text-secondary">{m.label}</dt>
                <dd>
                  <MetricCell metric={m} />
                </dd>
              </div>
            ))}
          </dl>
        </Section>
      )}

      <Section title="Decision timeline" description="Phases in the order they were built, each measured on its own frozen dataset.">
        <DecisionTimeline catalog={catalog} />
      </Section>

      <div className="mt-8">
        <Caveats caveats={catalog.caveats} />
      </div>
    </div>
  );
}

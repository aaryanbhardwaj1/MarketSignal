"use client";

import { Fragment } from "react";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { CardGridSkeleton, ErrorState } from "@/components/ui/states";
import { useInsights, useAnalyses } from "@/lib/api/hooks/insights";
import { indexAnalyses } from "@/lib/insights-view";
import { BriefMeta, DriftCallout, NoBriefState } from "./brief-parts";
import { OpportunityCard } from "./opportunity-card";

const WORKFLOW = ["Evidence", "Synthesis", "Hypothesis", "Strategic implication", "Next action"];

/** How an opportunity is built, in one quiet line. */
export function WorkflowStrip() {
  return (
    <ol aria-label="How an opportunity is built" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-secondary">
      {WORKFLOW.map((step, i) => (
        <Fragment key={step}>
          {i > 0 && (
            <li aria-hidden className="text-disabled">
              →
            </li>
          )}
          <li>{step}</li>
        </Fragment>
      ))}
    </ol>
  );
}

export function OpportunitiesList({ ws }: { ws: string }) {
  const brief = useInsights(ws);
  const analyses = useAnalyses(ws);
  const index = indexAnalyses(analyses.data?.analyses);

  return (
    <PageContainer>
      <PageHeader
        title="Growth Opportunities"
        description="Hypotheses for where the client could grow, each weighed against the evidence for and against it. Decision support for the engagement team, not a recommendation."
        meta={brief.data?.fixture_version ? <BriefMeta brief={brief.data} /> : undefined}
      />
      <div className="mt-6 flex flex-col gap-6">
        {brief.isPending ? (
          <CardGridSkeleton label="Loading growth opportunities" count={4} lines={5} columns="lg:grid-cols-2" padding="md" />
        ) : brief.isError ? (
          <ErrorState
            title="Growth opportunities could not be loaded"
            description="The brief is temporarily unavailable. Try again in a moment."
            retry={() => void brief.refetch()}
          />
        ) : !brief.data.fixture_version || brief.data.opportunities.length === 0 ? (
          <NoBriefState ws={ws} subject="Growth opportunities" />
        ) : (
          <>
            <div className="flex flex-col gap-2">
              <p className="text-sm text-muted">
                Each opportunity moves from cited evidence to a testable hypothesis and a next research step. Status
                reflects the balance of evidence; opportunities are not scored or ranked.
              </p>
              <WorkflowStrip />
            </div>
            <DriftCallout brief={brief.data} />
            <div className="grid gap-4 lg:grid-cols-2">
              {brief.data.opportunities.map((o) => (
                <OpportunityCard key={o.id} ws={ws} opportunity={o} analyses={index} />
              ))}
            </div>
          </>
        )}
      </div>
    </PageContainer>
  );
}

import type { ReactNode } from "react";
import type { EvalCatalog } from "@/lib/api/contracts";
import { sourceLocator } from "@/lib/eval-view";
import { formatDateTime, formatNumber } from "@/lib/format";
import { SourceRef } from "../metric-bits";
import { evaluatedModels, evaluatedSets, productionRetrieval } from "./derive";

export const DASHBOARD_SENTENCE =
  "How MarketSignal's retrieval and answering were chosen and verified — measured on frozen evaluation sets, including the experiments that failed.";

function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 text-sm text-primary">{children}</dd>
    </div>
  );
}

/**
 * "Current evaluated configuration": production retrieval, datasets with versions, splits and
 * question counts, generation model and catalog build time. Fields the catalog lacks are omitted.
 */
export function ConfigStrip({ catalog }: { catalog: EvalCatalog }) {
  const retrieval = productionRetrieval(catalog);
  const sets = evaluatedSets(catalog);
  const models = evaluatedModels(catalog);
  return (
    <section aria-label="Current evaluated configuration" className="rounded-lg border border-border bg-sunken px-4 py-3">
      <dl className="grid gap-x-8 gap-y-3 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_auto]">
        {retrieval && (
          <Field label="Production retrieval">
            <span className="font-medium">{retrieval.label}</span>
            <span className="text-secondary">: dense + lexical, parent-level fusion</span>
            {retrieval.reranker && (
              <span className="mt-0.5 flex items-center gap-2 text-secondary">
                Reranker {retrieval.rerankerOff ? "off" : "on"}
                <SourceRef
                  path={retrieval.reranker.source.path}
                  locator={sourceLocator(retrieval.reranker.source)}
                  note={retrieval.reranker.title}
                />
              </span>
            )}
          </Field>
        )}
        <Field label="Evaluation sets">
          <ul className="flex flex-wrap gap-x-5 gap-y-1">
            {sets.map((s) => (
              <li key={s.dataset} className="whitespace-nowrap">
                <span className="font-mono text-xs">{s.version ?? s.dataset}</span>
                <span className="ml-1.5 tabular-nums text-secondary">
                  {s.splits
                    .map((sp) => `${sp.split ?? "single set"} ${formatNumber(sp.questions)}`)
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ul>
          <span className="mt-0.5 block text-xs text-muted">Questions per split</span>
        </Field>
        <div className="flex flex-col gap-3">
          {models.length > 0 && (
            <Field label={models.length > 1 ? "Generation models" : "Generation model"}>
              <span className="font-mono text-xs">{models.join(", ")}</span>
            </Field>
          )}
          <Field label="Catalog built">
            <span className="tabular-nums">{formatDateTime(catalog.built_at)}</span>
          </Field>
        </div>
      </dl>
    </section>
  );
}

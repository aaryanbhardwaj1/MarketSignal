"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { Select } from "@/components/ui/form-controls";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, LoadingRegion, Skeleton } from "@/components/ui/states";
import type { EvalCatalog, EvalItem, EvalRunId } from "@/lib/api/contracts";
import { useEvalCatalog, useEvalItems } from "@/lib/api/hooks/evaluation";
import { cx } from "@/lib/cx";
import { armLabels, bucketLabel, evalHref, evalRunHref, isEvalRunId, pageWindow, parsePageParam, provenanceForRun } from "@/lib/eval-view";
import { formatNumber, humanize } from "@/lib/format";
import { CatalogProvider } from "./catalog-context";
import { CatalogLoading, CatalogProblem } from "./catalog-states";
import { ItemDetail } from "./item-detail";

const PAGE = 25;

/** Short status for the list: what went wrong, from stored fields only. */
function itemFlag(item: EvalItem): { label: string; tone: "warn" | "danger" | "neutral" } | null {
  switch (item.phase) {
    case "retrieval":
      return item.bucket ? { label: item.bucket === "both_miss" ? "Missed" : "Differs", tone: item.bucket === "both_miss" ? "danger" : "warn" } : null;
    case "grounded":
      return item.failure ? { label: humanize(item.failure.final_classification), tone: "warn" } : null;
    case "analytics":
      if (!item.task_type_correct) return { label: "Misrouted", tone: "danger" };
      return item.values_matched === false ? { label: "Value mismatch", tone: "warn" } : null;
    case "research":
      return null;
  }
}

function ItemList({
  items,
  selected,
  onSelect,
}: {
  items: EvalItem[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul aria-label="Evaluation items" className="divide-y divide-border">
      {items.map((it) => {
        const flag = itemFlag(it);
        const active = it.item_id === selected;
        return (
          <li key={it.item_id}>
            <button
              type="button"
              aria-current={active ? "true" : undefined}
              onClick={() => onSelect(it.item_id)}
              className={cx(
                "flex w-full flex-col gap-1 px-3 py-2.5 text-left transition-colors",
                active ? "bg-accent-subtle" : "hover:bg-surface-muted",
              )}
            >
              <span className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-muted">{it.item_id}</span>
                {flag && <Badge tone={flag.tone}>{flag.label}</Badge>}
              </span>
              <span className="line-clamp-2 text-sm text-primary">{it.question}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function ItemListPanel({
  title,
  items,
  offset,
  selected,
  onSelect,
  onPage,
}: {
  title: string;
  items: ReturnType<typeof useEvalItems>;
  offset: number;
  selected: string | null;
  onSelect: (id: string) => void;
  onPage: (offset: number) => void;
}) {
  const list = items.data?.items ?? [];
  const total = items.data?.total ?? 0;
  return (
    <Card padding="none">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
        <p className="text-sm font-medium text-secondary">{title}</p>
        {items.data && <p className="text-xs tabular-nums text-muted">{pageWindow(offset, list.length, total)}</p>}
      </div>
      {items.isPending ? (
        <div className="p-3">
          <LoadingRegion label="Loading items" lines={8} />
        </div>
      ) : items.isError ? (
        <div className="p-3">
          <ErrorState
            title="Items could not be loaded"
            description="The items for this run were not returned."
            error={items.error}
            retry={() => void items.refetch()}
            devDetail={items.error instanceof Error ? items.error.message : undefined}
          />
        </div>
      ) : list.length === 0 ? (
        <p className="px-3 py-6 text-center text-sm text-muted">No items in this bucket.</p>
      ) : (
        <ItemList items={list} selected={selected} onSelect={onSelect} />
      )}
      {total > PAGE && (
        <nav aria-label="Item pages" className="flex items-center justify-between gap-2 border-t border-border px-3 py-2">
          <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onPage(Math.max(offset - PAGE, 0))}>
            Previous
          </Button>
          <Button variant="secondary" size="sm" disabled={offset + PAGE >= total} onClick={() => onPage(offset + PAGE)}>
            Next
          </Button>
        </nav>
      )}
    </Card>
  );
}

function RunBody({ catalog, ws, runId }: { catalog: EvalCatalog; ws: string; runId: EvalRunId }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const run = catalog.failure_runs.find((r) => r.run_id === runId);
  const bucket = params.get("bucket") || null;
  const validBucket = bucket && run?.buckets.some((b) => b.id === bucket) ? bucket : null;
  const offset = (parsePageParam(params.get("page")) - 1) * PAGE;
  const items = useEvalItems(runId, { offset, limit: PAGE, bucket: validBucket });
  const list = items.data?.items ?? [];
  const selectedId = params.get("item") ?? list[0]?.item_id ?? null;
  const selected = list.find((i) => i.item_id === selectedId) ?? null;

  /** Bucket and page changes clear the item (it may not be on the new page); page changes are history entries. */
  const navigate = (patch: Record<string, string | null>, mode: "push" | "replace") => {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    const qs = next.toString();
    router[mode](qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const bucketOptions = [
    { value: "", label: `All items (${formatNumber(run?.item_count)})` },
    ...(run?.buckets ?? []).map((b) => ({ value: b.id, label: `${b.label} (${formatNumber(b.n)})` })),
  ];

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumb={[
          { label: "RAG Evaluation", href: evalHref(ws) },
          { label: "Failure analysis", href: evalHref(ws, "failures") },
        ]}
        title={run?.label ?? runId}
        description="Every item from this run is preserved, including failures. Review the question, the expected evidence, what was retrieved or cited, and the stored checks."
      />
      <div className="mt-5 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm text-muted">
          Evaluation run
          <Select
            value={runId}
            onChange={(e) => router.push(evalRunHref(ws, e.target.value as EvalRunId))}
            options={catalog.failure_runs.map((r) => ({ value: r.run_id, label: r.label }))}
            className="min-w-72"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-muted">
          Failure bucket
          <Select
            value={validBucket ?? ""}
            onChange={(e) => navigate({ bucket: e.target.value || null, page: null, item: null }, "replace")}
            options={bucketOptions}
            className="min-w-72"
          />
        </label>
        {run && (
          <p className="pb-2 text-sm text-muted">
            Bucket source: <span className="font-mono">{run.bucket_field}</span>
          </p>
        )}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-12">
        <aside className="lg:col-span-4">
          <ItemListPanel
            title={bucketLabel(catalog, runId, validBucket)}
            items={items}
            offset={offset}
            selected={selected?.item_id ?? null}
            onSelect={(id) => navigate({ item: id }, "replace")}
            onPage={(next) => navigate({ page: next > 0 ? String(next / PAGE + 1) : null, item: null }, "push")}
          />
        </aside>
        <div className="min-w-0 lg:col-span-8">
          {items.isPending ? (
            <Skeleton height="24rem" />
          ) : selected ? (
            <ItemDetail item={selected} provenance={provenanceForRun(catalog, runId)} armLabels={armLabels(catalog)} />
          ) : list.length > 0 ? (
            <EmptyState title="Item not on this page" description="Select an item from the list to review it." />
          ) : (
            <EmptyState title="Nothing to review" description="This bucket has no items for the selected run." />
          )}
        </div>
      </div>
    </PageContainer>
  );
}

export function RunView({ ws, runId }: { ws: string; runId: string }) {
  const catalog = useEvalCatalog();
  if (!isEvalRunId(runId)) {
    return (
      <PageContainer width="wide">
        <PageHeader breadcrumb={[{ label: "RAG Evaluation", href: evalHref(ws) }]} title="Evaluation run not found" />
        <div className="mt-6">
          <Callout tone="neutral" title="There is no evaluation run with this identifier.">
            Choose a run from Failure analysis.
          </Callout>
        </div>
      </PageContainer>
    );
  }
  if (catalog.isPending || catalog.isError || !catalog.data) {
    return (
      <PageContainer width="wide">
        <PageHeader breadcrumb={[{ label: "RAG Evaluation", href: evalHref(ws) }]} title="Failure analysis" />
        <div className="mt-6">
          {catalog.isPending ? <CatalogLoading /> : <CatalogProblem error={catalog.error} retry={() => void catalog.refetch()} />}
        </div>
      </PageContainer>
    );
  }
  return (
    <CatalogProvider catalog={catalog.data}>
      <RunBody key={runId} catalog={catalog.data} ws={ws} runId={runId} />
    </CatalogProvider>
  );
}

"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { workspaceBase } from "@/components/shell/nav";
import { LoadingRegion } from "@/components/ui/states";
import type { AnalyticsResultSummary, ConversationSummary } from "@/lib/api/contracts";
import { useAnalyticsResults, useConversations, useDatasets } from "@/lib/api/hooks/core";
import { formatRelativeDate } from "@/lib/format";
import { rowsMatchedText } from "@/lib/insights-view";
import { runMode, toolStep } from "@/lib/labels";

const LIMIT = 5;

function ActivityList({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-surface">
      <div className="border-b border-border px-5 py-3">
        <h3 className="text-base font-semibold text-primary">{title}</h3>
        <p className="mt-0.5 text-sm text-muted">{description}</p>
      </div>
      <div className="px-5 py-2">{children}</div>
    </div>
  );
}

function Row({ href, title, meta }: { href: string | null; title: string; meta: string }) {
  return (
    <li className="py-2.5">
      {href ? (
        <Link href={href} className="block truncate rounded-sm text-base text-primary hover:text-accent-text hover:underline" title={title}>
          {title}
        </Link>
      ) : (
        <p className="truncate text-base text-primary" title={title}>
          {title}
        </p>
      )}
      <p className="mt-0.5 truncate text-sm text-muted">{meta}</p>
    </li>
  );
}

function Quiet({ children }: { children: ReactNode }) {
  return <p className="py-3 text-sm text-muted">{children}</p>;
}

function conversationMeta(c: ConversationSummary): string {
  const parts = [c.last_run ? runMode(c.last_run.mode).label : null, formatRelativeDate(c.updated_at)];
  return parts.filter(Boolean).join(" · ");
}

/** Featured conversations first; a workspace without featured ones shows its most recent research. */
function SavedResearch({ ws }: { ws: string }) {
  const featured = useConversations(ws, { featured: true, limit: LIMIT });
  const featuredItems = featured.data?.pages.flatMap((p) => p.items) ?? [];
  const useRecent = featured.isSuccess && featuredItems.length === 0;
  const recent = useConversations(ws, { limit: LIMIT });
  const q = useRecent ? recent : featured;
  const items = (q.data?.pages.flatMap((p) => p.items) ?? []).slice(0, LIMIT);
  return (
    <ActivityList
      title={useRecent ? "Recent research" : "Saved research"}
      description={
        useRecent ? "The latest research conversations, with cited answers." : "Featured research conversations, with cited answers."
      }
    >
      {q.isPending ? (
        <LoadingRegion label="Loading saved research" lines={4} />
      ) : q.isError ? (
        <Quiet>Saved research could not be loaded.</Quiet>
      ) : items.length === 0 ? (
        <Quiet>No research conversations yet. Questions asked in Ask MarketSignal are saved here.</Quiet>
      ) : (
        <ul className="divide-y divide-border">
          {items.map((c) => (
            <Row
              key={c.conversation_id}
              href={`${workspaceBase(ws)}/ask/${encodeURIComponent(c.conversation_id)}`}
              title={c.title}
              meta={conversationMeta(c)}
            />
          ))}
        </ul>
      )}
    </ActivityList>
  );
}

function resultTitle(r: AnalyticsResultSummary, datasetTitles: ReadonlyMap<string, string>): string {
  const dataset = datasetTitles.get(r.dataset) ?? "a structured dataset";
  return `${toolStep(r.tool).label} from ${dataset}`;
}

function RecentAnalyses({ ws }: { ws: string }) {
  const q = useAnalyticsResults(ws, { limit: LIMIT });
  const datasets = useDatasets(ws);
  const titles = new Map((datasets.data?.datasets ?? []).map((d) => [d.dataset, d.title]));
  const items = (q.data?.pages.flatMap((p) => p.items) ?? []).slice(0, LIMIT);
  return (
    <ActivityList title="Recent computed analyses" description="Figures computed from datasets during research.">
      {q.isPending ? (
        <LoadingRegion label="Loading recent analyses" lines={4} />
      ) : q.isError ? (
        <Quiet>Recent analyses could not be loaded.</Quiet>
      ) : items.length === 0 ? (
        <Quiet>No computed analyses yet.</Quiet>
      ) : (
        <ul className="divide-y divide-border">
          {items.map((r) => (
            <Row
              key={r.result_id}
              href={r.conversation_id ? `${workspaceBase(ws)}/ask/${encodeURIComponent(r.conversation_id)}` : null}
              title={resultTitle(r, titles)}
              meta={[rowsMatchedText(r), formatRelativeDate(r.created_at)].filter(Boolean).join(" · ")}
            />
          ))}
        </ul>
      )}
    </ActivityList>
  );
}

export function RecentActivity({ ws }: { ws: string }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SavedResearch ws={ws} />
      <RecentAnalyses ws={ws} />
    </div>
  );
}

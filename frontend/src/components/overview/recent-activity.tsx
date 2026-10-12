"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Card, CardHeader } from "@/components/ui/card";
import { LoadingRegion } from "@/components/ui/states";
import type { ConversationSummary } from "@/lib/api/contracts";
import { useAnalyticsResults, useConversations, useDatasets } from "@/lib/api/hooks/core";
import { formatRelativeDate } from "@/lib/format";
import { rowsMatchedText } from "@/lib/insights-view";
import { runMode } from "@/lib/labels";
import { collapseRepeats, describeResult, resultTitle } from "@/lib/result-summary";
import { askHref } from "@/lib/routes";

const LIMIT = 5;
/** Fetch a few extra so collapsing repeats still fills the list. */
const FETCH = 10;

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
    <Card padding="none" className="min-w-0">
      <CardHeader title={title} meta={description} />
      <div className="px-5 py-2">{children}</div>
    </Card>
  );
}

function Row({ href, title, meta }: { href: string | null; title: string; meta: string }) {
  return (
    <li className="py-2.5">
      {href ? (
        <Link href={href} className="line-clamp-2 rounded-sm text-base text-primary hover:text-accent-text hover:underline" title={title}>
          {title}
        </Link>
      ) : (
        <p className="line-clamp-2 text-base text-primary" title={title}>
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

/** The same question asked twice (for example in both research modes) is listed once, most recent first. */
function uniqueByTitle(items: readonly ConversationSummary[]): ConversationSummary[] {
  const seen = new Set<string>();
  return items.filter((c) => {
    const key = c.title.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Featured conversations first; a workspace without featured ones shows its most recent research. */
function SavedResearch({ ws }: { ws: string }) {
  const featured = useConversations(ws, { featured: true, limit: FETCH });
  const featuredItems = featured.data?.pages.flatMap((p) => p.items) ?? [];
  const useRecent = featured.isSuccess && featuredItems.length === 0;
  const recent = useConversations(ws, { limit: FETCH });
  const q = useRecent ? recent : featured;
  const items = uniqueByTitle(q.data?.pages.flatMap((p) => p.items) ?? []).slice(0, LIMIT);
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
              href={askHref(ws, c.conversation_id)}
              title={c.title}
              meta={conversationMeta(c)}
            />
          ))}
        </ul>
      )}
    </ActivityList>
  );
}

function RecentAnalyses({ ws }: { ws: string }) {
  const q = useAnalyticsResults(ws, { limit: FETCH });
  const datasets = useDatasets(ws);
  const info = new Map((datasets.data?.datasets ?? []).map((d) => [d.dataset, d]));
  const items = collapseRepeats(q.data?.pages.flatMap((p) => p.items) ?? []).slice(0, LIMIT);
  return (
    <ActivityList title="Recent saved results" description="Figures computed from datasets while answering research questions.">
      {q.isPending ? (
        <LoadingRegion label="Loading recent saved results" lines={4} />
      ) : q.isError ? (
        <Quiet>Recent saved results could not be loaded.</Quiet>
      ) : items.length === 0 ? (
        <Quiet>No saved results yet.</Quiet>
      ) : (
        <ul className="divide-y divide-border">
          {items.map((r) => (
            <Row
              key={r.result_id}
              href={r.conversation_id ? askHref(ws, r.conversation_id) : null}
              title={resultTitle(r, info.get(r.dataset))}
              meta={[describeResult(r).filters.join(", ") || info.get(r.dataset)?.title, rowsMatchedText(r), formatRelativeDate(r.created_at)]
                .filter(Boolean)
                .join(" · ")}
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

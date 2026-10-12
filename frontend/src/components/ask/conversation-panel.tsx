"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { LoadMore } from "@/components/ui/load-more";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status-indicator";
import type { ConversationSummary } from "@/lib/api/contracts";
import { useConversations } from "@/lib/api/hooks/core";
import { cx } from "@/lib/cx";
import { formatRelativeDate } from "@/lib/format";
import { conversationOutcome, modeLabel } from "@/lib/saved-run";
import { askHref } from "./ask-routes";

function ConversationRow({ ws, row, selected }: { ws: string; row: ConversationSummary; selected: boolean }) {
  const outcome = conversationOutcome(row);
  return (
    <li>
      <Link
        href={askHref(ws, row.conversation_id)}
        aria-current={selected ? "page" : undefined}
        className={cx(
          "block rounded-md px-2.5 py-2 hover:bg-surface-muted",
          selected && "bg-accent-subtle hover:bg-accent-subtle",
        )}
      >
        <span className="line-clamp-2 text-sm font-medium text-primary">{row.title || "Untitled conversation"}</span>
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          {row.last_run && <Badge>{modeLabel(row.last_run.mode)}</Badge>}
          {outcome && <StatusIndicator tone={outcome.tone} label={outcome.label} className="text-xs" />}
          <span className="ml-auto whitespace-nowrap">{formatRelativeDate(row.updated_at)}</span>
        </span>
      </Link>
    </li>
  );
}

function RowSkeleton() {
  return (
    <div className="flex flex-col gap-3 px-2.5 py-2" aria-hidden>
      <Skeleton lines={2} />
      <Skeleton lines={2} />
    </div>
  );
}

function GroupHeading({ children }: { children: string }) {
  return <h2 className="px-2.5 pb-1 pt-3 text-xs font-medium text-muted">{children}</h2>;
}

/** Saved conversations: the curated "Featured" list, then all conversations with search. */
export function ConversationPanel({ ws }: { ws: string }) {
  const params = useParams<{ conversationId?: string }>();
  const selectedId = params.conversationId ?? null;
  const [q, setQ] = useState("");
  const featured = useConversations(ws, { featured: true });
  const all = useConversations(ws, { q });
  const featuredRows = featured.data?.pages.flatMap((p) => p.items) ?? [];
  const allRows = all.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <nav aria-label="Conversations" className="flex min-h-0 flex-col">
      <div className="flex flex-col gap-2 border-b border-border px-3 py-3">
        <Link
          href={askHref(ws)}
          className="inline-flex h-8 items-center justify-center rounded-md border border-border-strong bg-surface px-3 text-sm font-medium text-primary hover:bg-surface-muted"
        >
          New conversation
        </Link>
        <SearchInput id="conversation-search" label="Search conversations" placeholder="Search conversations" onSubmit={setQ} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-4">
        {!q && (
          <>
            <GroupHeading>Featured</GroupHeading>
            {featured.isPending ? (
              <RowSkeleton />
            ) : featured.isError ? (
              <p className="px-2.5 text-sm text-muted">Featured conversations could not be loaded.</p>
            ) : featuredRows.length === 0 ? (
              <p className="px-2.5 text-sm text-muted">No featured conversations yet.</p>
            ) : (
              <ul className="flex flex-col gap-0.5">
                {featuredRows.map((row) => (
                  <ConversationRow key={row.conversation_id} ws={ws} row={row} selected={row.conversation_id === selectedId} />
                ))}
              </ul>
            )}
          </>
        )}
        <GroupHeading>{q ? `Results for “${q}”` : "All conversations"}</GroupHeading>
        {all.isPending ? (
          <RowSkeleton />
        ) : all.isError ? (
          <p className="px-2.5 text-sm text-muted">Conversations could not be loaded.</p>
        ) : allRows.length === 0 ? (
          <p className="px-2.5 text-sm text-muted">{q ? "No conversations match this search." : "No conversations yet."}</p>
        ) : (
          <>
            <ul className="flex flex-col gap-0.5">
              {allRows.map((row) => (
                <ConversationRow key={row.conversation_id} ws={ws} row={row} selected={row.conversation_id === selectedId} />
              ))}
            </ul>
            <div className="px-2.5 pt-2">
              <LoadMore hasMore={Boolean(all.hasNextPage)} loading={all.isFetchingNextPage} onLoadMore={() => void all.fetchNextPage()} />
            </div>
          </>
        )}
      </div>
    </nav>
  );
}

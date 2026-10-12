"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/form-controls";
import { LoadMore } from "@/components/ui/load-more";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status-indicator";
import type { ConversationSummary } from "@/lib/api/contracts";
import { useConversations } from "@/lib/api/hooks/core";
import { cx } from "@/lib/cx";
import { formatRelativeDate } from "@/lib/format";
import { modeLabel } from "@/lib/run-mode";
import { conversationOutcome, isAnsweredConversation } from "@/lib/saved-run";
import { askHref } from "./ask-routes";

type OutcomeFilter = "answered" | "all";
const OUTCOME_OPTIONS = [
  { value: "answered", label: "Answered" },
  { value: "all", label: "All outcomes" },
];
/** Rows to show before "Load more"; the Answered filter keeps fetching pages until it has this many. */
const ROWS_PER_STEP = 20;

function ConversationRow({
  ws,
  row,
  selected,
  note,
}: {
  ws: string;
  row: ConversationSummary;
  selected: boolean;
  /** Secondary line, e.g. the relation to the row above. */
  note?: string;
}) {
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
        {note && <span className="mt-0.5 block text-xs text-secondary">{note}</span>}
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

function GroupHeading({ children, id }: { children: string; id?: string }) {
  return (
    <h2 id={id} className="text-xs font-medium text-muted">
      {children}
    </h2>
  );
}

export interface FeaturedEntry {
  row: ConversationSummary;
  /** Set on the second answer to a question that is also featured above it. */
  note?: string;
}

/**
 * Featured rows with repeated questions kept together (Research answer first) and the repeat
 * labelled, so a deliberate mode comparison does not read as a duplicate.
 */
export function featuredEntries(rows: readonly ConversationSummary[]): FeaturedEntry[] {
  const groups = new Map<string, ConversationSummary[]>();
  for (const row of rows) {
    const key = row.title.trim().toLowerCase();
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const rank = (row: ConversationSummary) => (row.last_run?.mode === "research" ? 0 : 1);
  return [...groups.values()].flatMap((group) =>
    [...group]
      .sort((a, b) => rank(a) - rank(b))
      .map((row, i) => (i === 0 ? { row } : { row, note: "Same question as above, answered for comparison" })),
  );
}

/** Keeps fetching pages while the Answered filter shows fewer rows than requested. */
function useFilteredRows(q: string, outcome: OutcomeFilter, ws: string) {
  const all = useConversations(ws, { q });
  const [request, setRequest] = useState({ key: "", target: ROWS_PER_STEP });
  const key = `${q}|${outcome}`;
  const target = request.key === key ? request.target : ROWS_PER_STEP;
  const loaded = all.data?.pages.flatMap((p) => p.items) ?? [];
  const rows = outcome === "answered" ? loaded.filter(isAnsweredConversation) : loaded;
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = all;
  const needMore = outcome === "answered" && rows.length < target && hasNextPage && !isFetchingNextPage && !isFetchNextPageError;

  useEffect(() => {
    if (needMore) void fetchNextPage();
  }, [needMore, fetchNextPage]);

  const loadMore = () => {
    setRequest({ key, target: rows.length + ROWS_PER_STEP });
    if (outcome === "all") void fetchNextPage();
  };
  return { all, rows, hidden: loaded.length - rows.length, filling: needMore || isFetchingNextPage, loadMore };
}

/** Saved conversations: the curated "Featured" list, then all conversations with search and an outcome filter. */
export function ConversationPanel({ ws }: { ws: string }) {
  const params = useParams<{ conversationId?: string }>();
  const selectedId = params.conversationId ?? null;
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState<OutcomeFilter>("answered");
  const featured = useConversations(ws, { featured: true });
  const featuredRows = featuredEntries(featured.data?.pages.flatMap((p) => p.items) ?? []);
  const { all, rows, hidden, filling, loadMore } = useFilteredRows(q, outcome, ws);
  const answeredOnly = outcome === "answered";

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
            <div className="px-2.5 pb-1 pt-3">
              <GroupHeading>Featured</GroupHeading>
            </div>
            {featured.isPending ? (
              <RowSkeleton />
            ) : featured.isError ? (
              <p className="px-2.5 text-sm text-muted">Featured conversations could not be loaded.</p>
            ) : featuredRows.length === 0 ? (
              <p className="px-2.5 text-sm text-muted">No featured conversations yet.</p>
            ) : (
              <ul className="flex flex-col gap-0.5">
                {featuredRows.map(({ row, note }) => (
                  <ConversationRow key={row.conversation_id} ws={ws} row={row} note={note} selected={row.conversation_id === selectedId} />
                ))}
              </ul>
            )}
          </>
        )}
        <div className="flex items-center justify-between gap-2 px-2.5 pb-1 pt-3">
          <GroupHeading>{q ? `Results for “${q}”` : "All conversations"}</GroupHeading>
          <label htmlFor="conversation-outcome" className="sr-only">
            Show conversations
          </label>
          <Select
            id="conversation-outcome"
            controlSize="sm"
            className="w-32 shrink-0"
            value={outcome}
            options={OUTCOME_OPTIONS}
            onChange={(e) => setOutcome(e.target.value === "all" ? "all" : "answered")}
          />
        </div>
        {all.isPending ? (
          <RowSkeleton />
        ) : all.isError ? (
          <p className="px-2.5 text-sm text-muted">Conversations could not be loaded.</p>
        ) : rows.length === 0 && filling ? (
          <RowSkeleton />
        ) : rows.length === 0 ? (
          <p className="px-2.5 text-sm text-muted">
            {q ? "No conversations match this search." : answeredOnly && hidden > 0 ? "No answered conversations yet." : "No conversations yet."}
            {answeredOnly && hidden > 0 && " Choose All outcomes to include unanswered ones."}
          </p>
        ) : (
          <>
            <ul className="flex flex-col gap-0.5">
              {rows.map((row) => (
                <ConversationRow key={row.conversation_id} ws={ws} row={row} selected={row.conversation_id === selectedId} />
              ))}
            </ul>
            <div className="px-2.5 pt-2">
              <LoadMore hasMore={Boolean(all.hasNextPage)} loading={filling} onLoadMore={loadMore} />
            </div>
          </>
        )}
      </div>
    </nav>
  );
}

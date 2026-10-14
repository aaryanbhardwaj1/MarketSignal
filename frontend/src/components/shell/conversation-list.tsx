"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { LoadMore } from "@/components/ui/load-more";
import type { ConversationSummary } from "@/lib/api/contracts";
import { useConversations } from "@/lib/api/hooks/core";
import { cx } from "@/lib/cx";
import { formatRelativeDate } from "@/lib/format";
import { askHref } from "@/lib/routes";
import { isAnsweredConversation } from "@/lib/saved-run";
import { conversationTitle, featuredEntries, groupByRecency } from "./conversation-groups";

/** Rows to show before fetching more; the Answered filter keeps fetching pages until it has this many. */
const ROWS_PER_STEP = 20;

function ConversationRow({
  ws,
  row,
  selected,
  note,
  onNavigate,
}: {
  ws: string;
  row: ConversationSummary;
  selected: boolean;
  note?: string;
  onNavigate?: () => void;
}) {
  const title = conversationTitle(row.title);
  return (
    <li>
      <Link
        href={askHref(ws, row.conversation_id)}
        aria-current={selected ? "page" : undefined}
        title={title}
        data-conversation-row=""
        onClick={onNavigate}
        className={cx(
          "group flex h-8 items-center gap-2 rounded-md px-2.5 text-sm transition-colors duration-(--duration-fast) focus-visible:outline-offset-[-2px]",
          selected ? "bg-accent-subtle font-medium text-accent-text" : "text-secondary hover:bg-surface-muted hover:text-primary",
          note && "h-auto py-1.5",
        )}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate">{title}</span>
          {note && <span className="block text-xs font-normal text-muted">{note}</span>}
        </span>
        {/* Hidden (not just transparent) when idle, so titles use the full row width. */}
        <span
          className={cx(
            "shrink-0 text-2xs font-normal text-muted tabular-nums",
            selected ? "block" : "hidden group-hover:block group-focus-visible:block",
          )}
        >
          {formatRelativeDate(row.updated_at)}
        </span>
      </Link>
    </li>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="pt-3 first:pt-1">
      <h3 className="px-2.5 pb-1 text-xs font-medium text-muted">{label}</h3>
      <ul className="flex flex-col gap-px">{children}</ul>
    </div>
  );
}

function RowsSkeleton() {
  return (
    <div className="flex flex-col gap-2 px-2.5 pt-2" aria-hidden>
      {[72, 88, 64, 80].map((w) => (
        <span key={w} className="ms-skeleton block h-4 rounded-sm" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

const Quiet = ({ children }: { children: ReactNode }) => <p className="px-2.5 pt-2 text-sm text-muted">{children}</p>;

/** Keeps fetching pages while the Answered filter shows fewer rows than requested. */
function useFilteredRows(ws: string, q: string, answeredOnly: boolean) {
  const all = useConversations(ws, { q });
  const [request, setRequest] = useState({ key: "", target: ROWS_PER_STEP });
  const key = `${q}|${answeredOnly}`;
  const target = request.key === key ? request.target : ROWS_PER_STEP;
  const loaded = all.data?.pages.flatMap((p) => p.items) ?? [];
  const rows = answeredOnly ? loaded.filter(isAnsweredConversation) : loaded;
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = all;
  const needMore = answeredOnly && rows.length < target && hasNextPage && !isFetchingNextPage && !isFetchNextPageError;

  useEffect(() => {
    if (needMore) void fetchNextPage();
  }, [needMore, fetchNextPage]);

  const loadMore = () => {
    if (isFetchingNextPage) return;
    setRequest({ key, target: rows.length + ROWS_PER_STEP });
    if (!answeredOnly) void fetchNextPage();
  };
  return { all, rows, hidden: loaded.length - rows.length, filling: needMore || isFetchingNextPage, loadMore };
}

/** Fires `onVisible` when the sentinel scrolls into view (auto "load more"). */
function useAutoLoad(onVisible: () => void, enabled: boolean) {
  const sentinel = useRef<HTMLDivElement>(null);
  const latest = useRef(onVisible);
  useEffect(() => {
    latest.current = onVisible;
  });
  useEffect(() => {
    const el = sentinel.current;
    if (!enabled || !el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) latest.current();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [enabled]);
  return sentinel;
}

/** Arrow keys, Home and End move between conversation rows. */
function onListKeyDown(event: KeyboardEvent<HTMLElement>) {
  const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
  if (!keys.includes(event.key)) return;
  const rows = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("[data-conversation-row]"));
  if (rows.length === 0) return;
  const index = rows.indexOf(document.activeElement as HTMLElement);
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? rows.length - 1
        : event.key === "ArrowDown"
          ? Math.min(rows.length - 1, index + 1)
          : Math.max(0, index - 1);
  event.preventDefault();
  rows[next]?.focus();
}

/**
 * Conversation history: "Saved research" (featured, comparison repeats labelled) and then
 * recency groups. A search shows matching conversations grouped by recency only.
 */
export function ConversationList({
  ws,
  q,
  answeredOnly,
  now,
  onNavigate,
}: {
  ws: string;
  q: string;
  answeredOnly: boolean;
  /** Reference time for the recency groups. */
  now: Date;
  onNavigate?: () => void;
}) {
  const params = useParams<{ conversationId?: string }>();
  const selectedId = params?.conversationId ?? null;
  const featured = useConversations(ws, { featured: true });
  const featuredRows = q ? [] : featuredEntries(featured.data?.pages.flatMap((p) => p.items) ?? []);
  const featuredIds = new Set(featuredRows.map((f) => f.row.conversation_id));
  const { all, rows, hidden, filling, loadMore } = useFilteredRows(ws, q, answeredOnly);
  const recent = groupByRecency(
    rows.filter((r) => !featuredIds.has(r.conversation_id)),
    now,
  );
  const sentinel = useAutoLoad(loadMore, Boolean(all.hasNextPage) && !filling);

  const rowProps = (row: ConversationSummary) => ({
    ws,
    row,
    selected: row.conversation_id === selectedId,
    onNavigate,
  });

  return (
    <div onKeyDown={onListKeyDown} className="pb-4">
      {!q && featuredRows.length > 0 && (
        <Group label="Saved research">
          {featuredRows.map(({ row, note }) => (
            <ConversationRow key={row.conversation_id} {...rowProps(row)} note={note} />
          ))}
        </Group>
      )}
      {!q && featured.isError && <Quiet>Saved research could not be loaded.</Quiet>}
      {all.isPending || (featured.isPending && !q) ? (
        <RowsSkeleton />
      ) : all.isError ? (
        <Quiet>Conversations could not be loaded.</Quiet>
      ) : recent.length === 0 && filling ? (
        <RowsSkeleton />
      ) : recent.length === 0 ? (
        <Quiet>
          {q ? "No conversations match this search." : featuredRows.length > 0 ? "No other conversations yet." : "No conversations yet."}
          {answeredOnly && hidden > 0 && " Turn off Answered only to include unanswered ones."}
        </Quiet>
      ) : (
        recent.map((group) => (
          <Group key={group.id} label={group.label}>
            {group.rows.map((row) => (
              <ConversationRow key={row.conversation_id} {...rowProps(row)} />
            ))}
          </Group>
        ))
      )}
      <div ref={sentinel} aria-hidden className="h-px" />
      {!all.isPending && !all.isError && (
        <div className="px-2.5">
          <LoadMore hasMore={Boolean(all.hasNextPage)} loading={filling} onLoadMore={loadMore} />
        </div>
      )}
    </div>
  );
}

/**
 * Pure helpers for the conversation sidebar: row titles, recency buckets and the featured
 * "Saved research" ordering. Kept free of React so they are unit-tested directly.
 */
import type { ConversationSummary } from "@/lib/api/contracts";

export const UNTITLED_CONVERSATION = "Untitled conversation";

/** Trailing sentence punctuation dropped from a title ("Why is Gen Z churning?" → "Why is Gen Z churning"). */
const TRAILING_PUNCTUATION = /[\s.?!,;:…–—-]+$/u;

/**
 * Single-line title for a row: the stored title (or first question), whitespace collapsed and
 * trailing punctuation removed. Closing brackets and quotes are kept. Visual clipping is CSS.
 */
export function conversationTitle(title: string | null | undefined): string {
  const collapsed = (title ?? "").replace(/\s+/g, " ").trim();
  const stripped = collapsed.replace(TRAILING_PUNCTUATION, "");
  return stripped || UNTITLED_CONVERSATION;
}

export type RecencyGroupId = "today" | "yesterday" | "week" | "month" | "older";

export const RECENCY_GROUPS: ReadonlyArray<{ id: RecencyGroupId; label: string }> = [
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "week", label: "Previous 7 days" },
  { id: "month", label: "Previous 30 days" },
  { id: "older", label: "Older" },
];

const DAY_MS = 86_400_000;

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** Calendar-day bucket (local time) of `iso` relative to `now`. Future dates count as today. */
export function recencyGroup(iso: string, now: Date): RecencyGroupId {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "older";
  // Round, not floor: a daylight-saving day is 23 or 25 hours long.
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days <= 7) return "week";
  if (days <= 30) return "month";
  return "older";
}

export interface ConversationGroup {
  id: RecencyGroupId;
  label: string;
  rows: ConversationSummary[];
}

/** Rows bucketed by `updated_at`, in group order; input order is kept inside a group; empty groups omitted. */
export function groupByRecency(rows: readonly ConversationSummary[], now: Date): ConversationGroup[] {
  const buckets = new Map<RecencyGroupId, ConversationSummary[]>();
  for (const row of rows) {
    const id = recencyGroup(row.updated_at, now);
    buckets.set(id, [...(buckets.get(id) ?? []), row]);
  }
  return RECENCY_GROUPS.filter((g) => buckets.has(g.id)).map((g) => ({ ...g, rows: buckets.get(g.id) ?? [] }));
}

export interface FeaturedEntry {
  row: ConversationSummary;
  /** Set on the second answer to a question that is also featured above it. */
  note?: string;
}

export const COMPARISON_NOTE = "Same question, for comparison";

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
    [...group].sort((a, b) => rank(a) - rank(b)).map((row, i) => (i === 0 ? { row } : { row, note: COMPARISON_NOTE })),
  );
}

import { describe, expect, it } from "vitest";
import type { ConversationSummary } from "@/lib/api/contracts";
import {
  COMPARISON_NOTE,
  UNTITLED_CONVERSATION,
  conversationTitle,
  featuredEntries,
  groupByRecency,
  recencyGroup,
} from "./conversation-groups";

// Local-time reference: Wednesday 14 Oct 2026, 10:30.
const NOW = new Date(2026, 9, 14, 10, 30);
const at = (day: number, hour = 12, month = 9) => new Date(2026, month, day, hour).toISOString();

function row(id: string, updated: string, extra: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    conversation_id: id,
    title: `Question ${id}`,
    title_source: "title",
    created_at: updated,
    updated_at: updated,
    message_count: 2,
    featured: false,
    last_run: null,
    ...extra,
  };
}

describe("recencyGroup", () => {
  it.each([
    [at(14, 0), "today"],
    [at(14, 23), "today"],
    [at(13, 23), "yesterday"],
    [at(13, 0), "yesterday"],
    [at(12), "week"],
    [at(7), "week"],
    [at(6), "month"],
    [at(14, 12, 8), "month"],
    [at(13, 12, 8), "older"],
    [new Date(2025, 0, 1).toISOString(), "older"],
  ])("%s → %s", (iso, group) => {
    expect(recencyGroup(iso, NOW)).toBe(group);
  });

  it("treats future timestamps as today and unparseable ones as older", () => {
    expect(recencyGroup(at(20), NOW)).toBe("today");
    expect(recencyGroup("not a date", NOW)).toBe("older");
  });
});

describe("groupByRecency", () => {
  it("orders groups, keeps row order inside a group and omits empty groups", () => {
    const rows = [row("a", at(14, 9)), row("b", at(1)), row("c", at(14, 8)), row("d", at(10))];
    const groups = groupByRecency(rows, NOW);
    expect(groups.map((g) => [g.label, g.rows.map((r) => r.conversation_id)])).toEqual([
      ["Today", ["a", "c"]],
      ["Previous 7 days", ["d"]],
      ["Previous 30 days", ["b"]],
    ]);
  });

  it("returns nothing for no rows", () => {
    expect(groupByRecency([], NOW)).toEqual([]);
  });
});

describe("conversationTitle", () => {
  it.each([
    ["Why is Gen Z churning?", "Why is Gen Z churning"],
    ["Compare the two pricing tiers...", "Compare the two pricing tiers"],
    ["What next?!  ", "What next"],
    ["Summarise:", "Summarise"],
    ["Growth in Q3 (EMEA)", "Growth in Q3 (EMEA)"],
    ['Is "drop culture" working?', 'Is "drop culture" working'],
    ["Line one\n  line two", "Line one line two"],
    ["Version 2.0", "Version 2.0"],
  ])("%j → %j", (input, expected) => {
    expect(conversationTitle(input)).toBe(expected);
  });

  it("falls back when there is nothing left", () => {
    expect(conversationTitle("")).toBe(UNTITLED_CONVERSATION);
    expect(conversationTitle("  ?  ")).toBe(UNTITLED_CONVERSATION);
    expect(conversationTitle(null)).toBe(UNTITLED_CONVERSATION);
  });
});

describe("featuredEntries", () => {
  it("keeps repeated questions together, research answer first, and labels the repeat", () => {
    const base = { status: "completed", termination_state: null, degradation_flags: [], created_at: "", finished_at: null };
    const quick = row("q", at(14), { title: "Same question", last_run: { ...base, run_id: "r1", mode: "quick" } as never });
    const research = row("r", at(14), { title: "same question ", last_run: { ...base, run_id: "r2", mode: "research" } as never });
    const other = row("o", at(14), { title: "Other" });
    const entries = featuredEntries([quick, other, research]);
    expect(entries.map((e) => [e.row.conversation_id, e.note])).toEqual([
      ["r", undefined],
      ["q", COMPARISON_NOTE],
      ["o", undefined],
    ]);
  });
});

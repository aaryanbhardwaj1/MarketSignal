/**
 * Pure view logic for the deck builder: picker groups and selection state, the request body,
 * the outline of the deck the server composed, and plain-language exclusions and errors.
 * Nothing here guesses deck content; the outline is read from the server preview.
 */

import type {
  Analysis,
  ClaimType,
  Deck,
  DeckExclusion,
  DeckRequest,
  DeckSlide,
  DeckSlideKind,
  InsightsBrief,
} from "@/lib/api/contracts";
import { describeError } from "@/lib/api/errors";
import { errorMessage } from "@/lib/labels";
import { insightsDeckHref } from "@/lib/routes";
import { INSIGHT_CATEGORIES, type ResolvedDeckSelection } from "@/lib/views/insights";
import type { EvidenceStatus } from "@/components/ui/status-pill";

export const DEFAULT_DECK_TITLE = "Strategic findings";
export const QUESTION_PLACEHOLDER = "Should Northstar launch personalization as a premium tier for Gen Z?";
/** Server limits (DeckRequest): longer text is a 422, so the inputs stop there. */
export const TITLE_MAX = 120;
export const QUESTION_MAX = 300;
export const SELECTION_LIMIT: Record<PickKind, number> = { signals: 30, opportunities: 10, analyses: 10 };

// ── selection ──────────────────────────────────────────────────────────────────────────────

export type PickKind = keyof ResolvedDeckSelection;
export type DeckPick = ResolvedDeckSelection;

export const EMPTY_PICK: DeckPick = { signals: [], opportunities: [], analyses: [] };

export function pickSize(pick: DeckPick): number {
  return pick.signals.length + pick.opportunities.length + pick.analyses.length;
}

export function isPicked(pick: DeckPick, kind: PickKind, id: string): boolean {
  return pick[kind].includes(id);
}

/** New selection with `id` added or removed; never mutates `pick`. */
export function togglePick(pick: DeckPick, kind: PickKind, id: string): DeckPick {
  const ids = pick[kind];
  const next = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
  return { ...pick, [kind]: next };
}

/** Whether another item of `kind` may be added (server caps each list). */
export function canAdd(pick: DeckPick, kind: PickKind): boolean {
  return pick[kind].length < SELECTION_LIMIT[kind];
}

/** The deck URL for this selection; `parseDeckSelection` reads it back unchanged. */
export function pickHref(ws: string, pick: DeckPick): string {
  return insightsDeckHref(ws, pick);
}

/** Ids that the brief/analyses do not know (stale links); they are left out of the request. */
export function unknownPicks(pick: DeckPick, known: KnownIds): DeckPick {
  return {
    signals: pick.signals.filter((id) => !known.signals.has(id)),
    opportunities: pick.opportunities.filter((id) => !known.opportunities.has(id)),
    analyses: pick.analyses.filter((id) => !known.analyses.has(id)),
  };
}

export function withoutUnknown(pick: DeckPick, known: KnownIds): DeckPick {
  return {
    signals: pick.signals.filter((id) => known.signals.has(id)),
    opportunities: pick.opportunities.filter((id) => known.opportunities.has(id)),
    analyses: pick.analyses.filter((id) => known.analyses.has(id)),
  };
}

/** Request body: trimmed text (omitted when blank, so the server default applies) + the ids. */
export function deckRequest(pick: DeckPick, title: string, question: string): DeckRequest {
  const t = title.trim().slice(0, TITLE_MAX);
  const q = question.trim().slice(0, QUESTION_MAX);
  return {
    ...(t ? { title: t } : {}),
    ...(q ? { question: q } : {}),
    signal_ids: pick.signals,
    opportunity_ids: pick.opportunities,
    analysis_ids: pick.analyses,
  };
}

// ── picker ─────────────────────────────────────────────────────────────────────────────────

export interface PickerItem {
  kind: PickKind;
  id: string;
  title: string;
  status: EvidenceStatus | null;
  claim: ClaimType | null;
  /** Short plain-language hint, e.g. the business area or "Figures not computed". */
  hint: string | null;
}

export interface PickerGroup {
  id: string;
  label: string;
  items: PickerItem[];
}

export interface KnownIds {
  signals: ReadonlySet<string>;
  opportunities: ReadonlySet<string>;
  analyses: ReadonlySet<string>;
}

type BriefLists = Pick<InsightsBrief, "signals" | "opportunities">;

export function knownIds(brief: BriefLists | undefined, analyses: readonly Analysis[] | undefined): KnownIds {
  return {
    signals: new Set((brief?.signals ?? []).map((s) => s.id)),
    opportunities: new Set((brief?.opportunities ?? []).map((o) => o.id)),
    analyses: new Set((analyses ?? []).map((a) => a.id)),
  };
}

/** Opportunities, then insights by category (brief order), then analyses; empty groups dropped. */
export function pickerGroups(brief: BriefLists | undefined, analyses: readonly Analysis[] | undefined): PickerGroup[] {
  const opportunities: PickerItem[] = (brief?.opportunities ?? []).map((o) => ({
    kind: "opportunities",
    id: o.id,
    title: o.title,
    status: o.status,
    claim: o.thesis_claim_type,
    hint: null,
  }));
  const signals = brief?.signals ?? [];
  const kinds = INSIGHT_CATEGORIES.filter((c) => c.id !== "opportunities");
  const insightGroups: PickerGroup[] = kinds.map((cat) => ({
    id: cat.id,
    label: cat.label,
    items: signals.filter((s) => s.kind === cat.id).map(signalItem),
  }));
  const known = new Set(kinds.map((c) => c.id as string));
  const other = signals.filter((s) => !s.kind || !known.has(s.kind)).map(signalItem);
  const analysisItems: PickerItem[] = (analyses ?? []).map((a) => ({
    kind: "analyses",
    id: a.id,
    title: a.title,
    status: null,
    claim: a.status === "computed" ? "derived" : null,
    hint: a.status === "computed" ? a.business_area : "Figures not computed",
  }));
  return [
    { id: "opportunities", label: "Growth opportunities", items: opportunities },
    ...insightGroups,
    { id: "other", label: "Other findings", items: other },
    { id: "analyses", label: "Analyses", items: analysisItems },
  ].filter((g) => g.items.length > 0);
}

function signalItem(s: InsightsBrief["signals"][number]): PickerItem {
  return { kind: "signals", id: s.id, title: s.title, status: s.status, claim: s.claim_type, hint: null };
}

/** Only the groups/items currently selected (the compact view before "Add more findings"). */
export function selectedGroups(groups: readonly PickerGroup[], pick: DeckPick): PickerGroup[] {
  return groups
    .map((g) => ({ ...g, items: g.items.filter((i) => isPicked(pick, i.kind, i.id)) }))
    .filter((g) => g.items.length > 0);
}

export function itemTitle(groups: readonly PickerGroup[], id: string): string | null {
  for (const g of groups) {
    const hit = g.items.find((i) => i.id === id);
    if (hit) return hit.title;
  }
  return null;
}

// ── outline ────────────────────────────────────────────────────────────────────────────────

export const SECTION_LABEL: Record<DeckSlideKind, string> = {
  title: "Title",
  summary: "Executive summary",
  customer_findings: "Key customer findings",
  quantitative: "Quantitative evidence",
  market_findings: "Competitor and market findings",
  opportunity: "Growth opportunities",
  risks: "Risks and blockers",
  next_steps: "Next steps",
  appendix: "Sources",
};

export interface OutlineSection {
  kind: DeckSlideKind;
  label: string;
  /** 1-based slide numbers in this section. */
  slides: number[];
  /** Distinct slide titles that add information beyond the section label. */
  titles: string[];
}

const CONTINUED = /\s*\(cont(inued|\.)?\)$/i;

/** The deck's sections in order, grouping consecutive slides of the same kind. */
export function deckOutline(deck: Pick<Deck, "slides">): OutlineSection[] {
  const out: OutlineSection[] = [];
  for (const slide of deck.slides) {
    const last = out[out.length - 1];
    const section = last && last.kind === slide.kind ? last : null;
    const title = slide.title.replace(CONTINUED, "");
    const extra = title !== SECTION_LABEL[slide.kind] && slide.kind !== "title" && isNamedSlide(slide);
    if (section) {
      out[out.length - 1] = {
        ...section,
        slides: [...section.slides, slide.index],
        titles: extra && !section.titles.includes(title) ? [...section.titles, title] : section.titles,
      };
    } else {
      out.push({ kind: slide.kind, label: SECTION_LABEL[slide.kind], slides: [slide.index], titles: extra ? [title] : [] });
    }
  }
  return out;
}

/** Slides titled after an item (an opportunity, a named analysis) rather than a fixed section. */
function isNamedSlide(slide: DeckSlide): boolean {
  return slide.kind === "opportunity" || (slide.kind === "quantitative" && slide.subtitle !== null);
}

export function slidesLabel(n: number): string {
  return `${n} slide${n === 1 ? "" : "s"}`;
}

// ── exclusions and errors ──────────────────────────────────────────────────────────────────

export interface ExclusionView {
  id: string;
  title: string;
  reason: string;
}

/** Excluded items with a readable title (never an id) and the server's plain reason. */
export function exclusionViews(excluded: readonly DeckExclusion[], groups: readonly PickerGroup[]): ExclusionView[] {
  return excluded.map((e) => ({ id: e.id, title: itemTitle(groups, e.id) ?? "A selected finding", reason: e.reason }));
}

const DECK_ERROR: Record<string, string> = {
  DECK_ITEMS_NOT_FOUND: "Some selected findings are no longer in this workspace. Remove them and try again.",
  DECK_EMPTY: "None of the selected findings still verify against the sources, so there is nothing to put in a presentation.",
  DECK_TOO_LARGE: "This selection is too large for one presentation. Remove a few findings and try again.",
  VALIDATION_ERROR: "The presentation request was not accepted. Check the title, question and selection.",
};

/** Plain-language message for a deck request failure; codes stay out of the business UI. */
export function deckErrorMessage(error: unknown): string {
  const { code } = describeError(error);
  return DECK_ERROR[code] ?? errorMessage(code).label;
}

/** Whether a failure is the caller's abort (not an error to show). */
export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

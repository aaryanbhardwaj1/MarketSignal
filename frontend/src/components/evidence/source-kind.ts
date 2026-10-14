/**
 * Plain label for what kind of source a passage comes from ("Survey", "Interview transcript",
 * "Strategy memo", "Competitor filing", "Spreadsheet"…). Derived from the source title, class and
 * file type; falls back to the file-type label, then to "Source".
 */
import { sourceType } from "@/lib/labels";

const TITLE_KINDS: readonly [RegExp, string][] = [
  [/\bsurvey\b/i, "Survey"],
  [/\binterviews?\b/i, "Interview transcript"],
  [/\bfocus group\b/i, "Focus group summary"],
  [/\bcall notes?\b|\banalyst call\b/i, "Call notes"],
  [/\breviews\b/i, "Customer reviews"],
  [/\bsupport themes?\b/i, "Support themes report"],
  [/\bmemo\b|\bstrategy\b|\bplanning\b/i, "Strategy memo"],
  [/\bpilot\b|\bstudy\b/i, "Research study"],
  [/\bweb snapshot\b|\bpositioning\b/i, "Web snapshot"],
  [/\bannual report\b|\binvestor\b|\b10-k\b|\bfiling\b/i, "Filing"],
  [/\bfinancial\b/i, "Financial summary"],
  [/\bperformance\b|\bsizing\b/i, "Spreadsheet"],
  [/\btrends?\b|\bnote\b/i, "Market report"],
];

const COMPETITOR_FILING = /\bannual report\b|\binvestor\b|\b10-k\b|\bfiling\b|\bdeck\b/i;

export function sourceKind(source: { title: string; source_type: string; source_class?: string | null }): string {
  const { title, source_class: cls } = source;
  if (cls === "competitor" && COMPETITOR_FILING.test(title)) return "Competitor filing";
  for (const [pattern, label] of TITLE_KINDS) {
    if (!pattern.test(title)) continue;
    if (label === "Strategy memo" && /\breview\b|\bdeck\b/i.test(title)) return "Strategy review";
    return label;
  }
  const type = sourceType(source.source_type);
  if (source.source_type === "xlsx" || source.source_type === "csv") return "Spreadsheet";
  return type.known ? type.label : "Source";
}

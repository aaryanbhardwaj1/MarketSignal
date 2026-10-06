/**
 * Validates the `sections` payload of a final answer / stored assistant message. The shape
 * depends on the outcome, so it is parsed into a tagged union and anything unrecognised falls
 * back to rendering the canonical `content` Markdown.
 */

export interface GeneratedSections {
  kind: "generated";
  answer: string[];
  findings: string[];
  conflicts: string[];
  interpretation: string[];
  gaps: string[];
}

export interface EvidenceOnlySections {
  kind: "evidence_only";
  units: string[];
  reason: string | null;
}

export interface AbstainedSections {
  kind: "abstained";
  answer: string[];
  gaps: string[];
}

export type AnswerSections =
  | GeneratedSections
  | EvidenceOnlySections
  | AbstainedSections
  | { kind: "none" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function units(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === "string" && v.trim().length > 0);
}

export function parseSections(raw: unknown): AnswerSections {
  if (!isRecord(raw)) return { kind: "none" };
  if (Array.isArray(raw.evidence_only)) {
    return {
      kind: "evidence_only",
      units: units(raw.evidence_only),
      reason: typeof raw.reason === "string" && raw.reason ? raw.reason : null,
    };
  }
  if (raw.abstained === true) {
    return { kind: "abstained", answer: units(raw.answer), gaps: units(raw.gaps) };
  }
  const generated: GeneratedSections = {
    kind: "generated",
    answer: units(raw.answer),
    findings: units(raw.findings),
    conflicts: units(raw.conflicts),
    interpretation: units(raw.interpretation),
    gaps: units(raw.gaps),
  };
  const total =
    generated.answer.length +
    generated.findings.length +
    generated.conflicts.length +
    generated.interpretation.length +
    generated.gaps.length;
  return total > 0 ? generated : { kind: "none" };
}

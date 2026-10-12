"use client";

import { createContext, useContext, useId, useMemo, type ReactNode } from "react";
import { Callout } from "@/components/ui/callout";
import { InferenceTag } from "@/components/ui/cite-chip";
import { datasetTerms, humanizeDatasetTerms } from "@/lib/analytics";
import { isResultCard, type AnyCitationCard, type CitationCard, type ResultCitationCard } from "@/lib/api/types";
import { parseSections, type AnswerSections } from "@/lib/answer-sections";
import { numberCitations, stripInference, type CitationContext } from "@/lib/citations";
import { isModelUnavailable } from "@/lib/model-availability";
import { AnalyticsResults, SupportingEvidenceList } from "./answer-evidence";
import { ChipNumberingContext } from "./citation-numbering";
import { SafeMarkdown } from "./safe-markdown";

/** Section title for the computed results an answer cites, and its hint. */
export const COMPUTED_FIGURES_TITLE = "Computed figures";
export const COMPUTED_FIGURES_HINT = "Calculated from workspace datasets";

/** Dataset codes named by the cited results (`knit_upper_durability`) and their plain wording. */
const TermsContext = createContext<ReadonlyMap<string, string>>(new Map());

/** Answer text with dataset codes in plain words; citation markers are left untouched. */
function usePlainText(text: string): string {
  const terms = useContext(TermsContext);
  return humanizeDatasetTerms(text, terms);
}

/** One titled block of the answer. Order and visibility are decided by `AnswerView`. */
function AnswerSection({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <h3 id={id} className="flex flex-wrap items-baseline gap-2 text-sm font-semibold text-primary">
        {title}
        {hint && <span className="font-normal text-muted">{hint}</span>}
      </h3>
      <div className="text-base leading-relaxed text-primary">{children}</div>
    </section>
  );
}

function Unit({ unit, ws, ctx }: { unit: string; ws: string; ctx: CitationContext }) {
  const { text, inferred } = stripInference(unit);
  const plain = usePlainText(text);
  return (
    <>
      <SafeMarkdown inline text={plain} ws={ws} citations={ctx} />
      {inferred && <InferenceTag />}
    </>
  );
}

function UnitList({ units, ws, ctx }: { units: readonly string[]; ws: string; ctx: CitationContext }) {
  return (
    <ul className="flex list-disc flex-col gap-1.5 pl-5 marker:text-muted">
      {units.map((unit, i) => (
        <li key={i}>
          <Unit unit={unit} ws={ws} ctx={ctx} />
        </li>
      ))}
    </ul>
  );
}

function PlainUnit({ unit, ws }: { unit: string; ws: string }) {
  return <SafeMarkdown inline text={usePlainText(stripInference(unit).text)} ws={ws} />;
}

function GapList({ units, ws }: { units: readonly string[]; ws: string }) {
  return (
    <ul className="flex flex-col gap-1.5 rounded-lg border border-dashed border-border-strong bg-surface-muted px-4 py-3 text-secondary">
      {units.map((unit, i) => (
        <li key={i}>
          <PlainUnit unit={unit} ws={ws} />
        </li>
      ))}
    </ul>
  );
}

/** Texts in display order, so citation numbers follow the order a reader meets them. */
function displayTexts(parsed: AnswerSections, content: string): string[] {
  switch (parsed.kind) {
    case "generated":
      return [...parsed.answer, ...parsed.interpretation, ...parsed.findings, ...parsed.conflicts];
    case "evidence_only":
      return parsed.units;
    case "abstained":
      return parsed.answer;
    default:
      return [content];
  }
}

interface BodyProps {
  ws: string;
  ctx: CitationContext;
  /** "Supporting evidence" section (null when nothing is cited). */
  evidence: ReactNode;
  /** "Computed figures" section (null when no result is cited). */
  figures: ReactNode;
}

function EvidenceOnlyBody({ parsed, ws, ctx, evidence, figures }: BodyProps & { parsed: Extract<AnswerSections, { kind: "evidence_only" }> }) {
  const unavailable = isModelUnavailable({ sectionsReason: parsed.reason });
  return (
    <>
      <Callout tone="warn" title={unavailable ? "Live model unavailable for this answer" : "No verified answer"}>
        {unavailable
          ? "Showing the retrieved evidence only."
          : "The written answer did not pass citation checks, so the most relevant evidence is shown instead."}
      </Callout>
      {parsed.units.length > 0 && (
        <AnswerSection title="Retrieved evidence">
          <UnitList units={parsed.units} ws={ws} ctx={ctx} />
        </AnswerSection>
      )}
      {evidence}
      {figures}
    </>
  );
}

function AbstainedBody({ parsed, ws }: { parsed: Extract<AnswerSections, { kind: "abstained" }>; ws: string }) {
  return (
    <>
      <Callout tone="neutral" title="Not enough evidence to answer">
        The workspace evidence does not support a defensible answer to this question.
      </Callout>
      {parsed.answer.length > 0 && (
        <p className="text-base leading-relaxed text-secondary">
          {parsed.answer.map((unit, i) => (
            <span key={i}>
              <PlainUnit unit={unit} ws={ws} />{" "}
            </span>
          ))}
        </p>
      )}
      {parsed.gaps.length > 0 && (
        <AnswerSection title="Evidence gaps">
          <GapList units={parsed.gaps} ws={ws} />
        </AnswerSection>
      )}
    </>
  );
}

function GeneratedBody({ parsed, ws, ctx, evidence, figures }: BodyProps & { parsed: Extract<AnswerSections, { kind: "generated" }> }) {
  const unknowns = new Set(parsed.answerUnknowns.map((u) => u.trim()));
  const answer = parsed.answer.filter((u) => !unknowns.has(u.trim()));
  const gaps = [...parsed.gaps, ...parsed.answer.filter((u) => unknowns.has(u.trim()))];
  return (
    <>
      {(answer.length > 0 || parsed.interpretation.length > 0) && (
        <AnswerSection title="Answer">
          {answer.length > 0 && (
            <p>
              {answer.map((unit, i) => (
                <span key={i}>
                  <Unit unit={unit} ws={ws} ctx={ctx} />{" "}
                </span>
              ))}
            </p>
          )}
          {parsed.interpretation.length > 0 && (
            <div className="mt-3 border-l-2 border-dashed border-border-strong pl-3">
              <p className="mb-1 flex items-center gap-1 text-sm font-medium text-secondary">
                Interpretation <InferenceTag />
              </p>
              <UnitList units={parsed.interpretation} ws={ws} ctx={ctx} />
            </div>
          )}
        </AnswerSection>
      )}
      {parsed.findings.length > 0 && (
        <AnswerSection title="Key findings">
          <UnitList units={parsed.findings} ws={ws} ctx={ctx} />
        </AnswerSection>
      )}
      {evidence}
      {parsed.conflicts.length > 0 && (
        <AnswerSection title="Conflicting evidence">
          <UnitList units={parsed.conflicts} ws={ws} ctx={ctx} />
        </AnswerSection>
      )}
      {figures}
      {gaps.length > 0 && (
        <AnswerSection title="Evidence gaps">
          <GapList units={gaps} ws={ws} />
        </AnswerSection>
      )}
    </>
  );
}

function PlainBody({ content, ws, ctx, evidence, figures }: BodyProps & { content: string }) {
  return (
    <>
      <AnswerSection title="Answer">
        <SafeMarkdown text={usePlainText(content)} ws={ws} citations={ctx} />
      </AnswerSection>
      {evidence}
      {figures}
    </>
  );
}

export interface AnswerViewProps {
  ws: string;
  content: string;
  citations: readonly AnyCitationCard[];
  sections: unknown;
  /** Source code → title, used to name the dataset behind a computed result. */
  sourceTitles?: Readonly<Record<string, string>>;
  /** Rendered last ("Suggested next step"); deterministic UI actions only. */
  nextSteps?: ReactNode;
}

function sourceTitleMap(citations: readonly AnyCitationCard[], sourceTitles?: Readonly<Record<string, string>>) {
  const map: Record<string, string> = { ...sourceTitles };
  for (const card of citations) if (!isResultCard(card) && !map[card.source_code]) map[card.source_code] = card.source_title;
  return map;
}

/**
 * Verified answer renderer, shared by the live `final` event and saved answers. Sections follow a
 * fixed order and empty ones are hidden: Answer, Key findings, Supporting evidence, Conflicting
 * evidence, Computed figures, Evidence gaps, Suggested next step.
 */
export function AnswerView({ ws, content, citations, sections, sourceTitles, nextSteps }: AnswerViewProps) {
  const parsed = useMemo(() => parseSections(sections), [sections]);
  const ctx = useMemo<CitationContext>(() => ({ cards: citations }), [citations]);
  const numbering = useMemo(() => numberCitations(displayTexts(parsed, content), citations), [parsed, content, citations]);
  const titles = useMemo(() => sourceTitleMap(citations, sourceTitles), [citations, sourceTitles]);
  const terms = useMemo(
    () => datasetTerms(citations.filter((c): c is ResultCitationCard => isResultCard(c)).map((c) => c.summary ?? "")),
    [citations],
  );

  const evidenceCards: readonly CitationCard[] = numbering.evidence;
  const evidence = evidenceCards.length > 0 && (
    <AnswerSection title="Supporting evidence" hint={`${evidenceCards.length} cited`}>
      <SupportingEvidenceList ws={ws} cards={evidenceCards} />
    </AnswerSection>
  );
  const figures = numbering.results.length > 0 && (
    <AnswerSection title={COMPUTED_FIGURES_TITLE} hint={COMPUTED_FIGURES_HINT}>
      <AnalyticsResults ws={ws} cards={numbering.results} sourceTitles={titles} />
    </AnswerSection>
  );
  const body = { ws, ctx, evidence, figures };

  return (
    <TermsContext.Provider value={terms}>
      <ChipNumberingContext.Provider value={numbering}>
        <div className="flex flex-col gap-6">
          {parsed.kind === "evidence_only" ? (
            <EvidenceOnlyBody parsed={parsed} {...body} />
          ) : parsed.kind === "abstained" ? (
            <AbstainedBody parsed={parsed} ws={ws} />
          ) : parsed.kind === "generated" ? (
            <GeneratedBody parsed={parsed} {...body} />
          ) : (
            <PlainBody content={content} {...body} />
          )}
          {nextSteps && <AnswerSection title="Suggested next step">{nextSteps}</AnswerSection>}
        </div>
      </ChipNumberingContext.Provider>
    </TermsContext.Provider>
  );
}

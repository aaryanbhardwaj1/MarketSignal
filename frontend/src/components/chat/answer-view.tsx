import Link from "next/link";
import { useMemo, type ReactNode } from "react";
import { isResultCard, type AnyCitationCard, type CitationCard } from "@/lib/api/types";
import { parseSections } from "@/lib/answer-sections";
import { stripInference, type CitationContext } from "@/lib/citations";
import { evidenceViewerHref } from "@/lib/handles";
import { humanize } from "@/lib/format";
import { Badge } from "../ui/badge";
import { SafeMarkdown } from "./safe-markdown";

interface UnitProps {
  unit: string;
  ws: string;
  citations: CitationContext;
  /** Answer sentences the backend flagged as unknowns / data gaps. */
  unknowns?: ReadonlySet<string>;
}

function InferenceLabel() {
  return (
    <span className="ml-1 inline-flex items-center rounded bg-violet-100 px-1.5 py-px align-middle text-[10px] font-semibold uppercase tracking-wide text-violet-700">
      Inference
    </span>
  );
}

function UnknownLabel() {
  return (
    <span className="mr-1.5 inline-flex items-center rounded bg-slate-200/70 px-1.5 py-px align-middle text-[10px] font-semibold uppercase tracking-wide text-slate-500">
      Unknown / evidence gap
    </span>
  );
}

/**
 * One answer sentence: evidence units read normally; `[inference]` units are set apart; a unit the
 * backend listed in `answer_unknowns` is styled as a gap.
 */
function AnswerUnit({ unit, ws, citations, unknowns }: UnitProps) {
  if (unknowns?.has(unit.trim())) {
    return (
      <span className="rounded bg-slate-50 px-0.5 text-slate-600">
        <UnknownLabel />
        <SafeMarkdown inline text={unit} ws={ws} citations={citations} />
      </span>
    );
  }
  const { text, inferred } = stripInference(unit);
  if (!inferred) return <SafeMarkdown inline text={text} ws={ws} citations={citations} />;
  return (
    <span className="rounded bg-violet-50/70 px-0.5 text-slate-700 italic decoration-violet-300">
      <SafeMarkdown inline text={text} ws={ws} citations={citations} />
      <InferenceLabel />
    </span>
  );
}

function SectionBlock({
  title,
  tone,
  hint,
  children,
}: {
  title: string;
  tone: "evidence" | "conflict" | "inference" | "gap";
  hint?: string;
  children: ReactNode;
}) {
  const tones = {
    evidence: "border-emerald-500/70",
    conflict: "border-amber-500/70",
    inference: "border-violet-400/70 bg-violet-50/40",
    gap: "border-slate-300 bg-slate-50 text-slate-600",
  } as const;
  return (
    <section className={`rounded-r-md border-l-2 py-1 pr-2 pl-3 ${tones[tone]}`}>
      <h3 className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
        {hint && <span className="font-normal normal-case tracking-normal text-slate-400">{hint}</span>}
      </h3>
      <div className="mt-1 text-sm text-slate-800">{children}</div>
    </section>
  );
}

function UnitList({ units, ws, citations }: { units: string[]; ws: string; citations: CitationContext }) {
  return (
    <ul className="list-disc space-y-1 pl-5">
      {units.map((unit, i) => (
        <li key={i} className="leading-relaxed">
          <AnswerUnit unit={unit} ws={ws} citations={citations} />
        </li>
      ))}
    </ul>
  );
}

function GapsPanel({ units, ws }: { units: string[]; ws: string }) {
  return (
    <SectionBlock title="Gaps & unknowns" tone="gap">
      <ul className="space-y-1">
        {units.map((unit, i) => (
          <li key={i} className="flex flex-wrap items-baseline gap-2 text-slate-600">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Unknown / evidence gap
            </span>
            <SafeMarkdown inline text={stripInference(unit).text} ws={ws} />
          </li>
        ))}
      </ul>
    </SectionBlock>
  );
}

function Banner({ tone, children }: { tone: "amber" | "slate"; children: ReactNode }) {
  const cls =
    tone === "amber"
      ? "border-amber-300 bg-amber-50 text-amber-900"
      : "border-slate-300 bg-slate-100 text-slate-800";
  return (
    <p role="status" className={`rounded-md border px-3 py-2 text-sm font-medium ${cls}`}>
      {children}
    </p>
  );
}

export function SourceList({ ws, cards }: { ws: string; cards: readonly AnyCitationCard[] }) {
  const evidence = useMemo(() => cards.filter((c): c is CitationCard => !isResultCard(c)), [cards]);
  return <EvidenceSources ws={ws} cards={evidence} />;
}

function EvidenceSources({ ws, cards }: { ws: string; cards: readonly CitationCard[] }) {
  if (cards.length === 0) return null;
  return (
    <details className="text-xs text-slate-600">
      <summary className="cursor-pointer select-none font-medium text-slate-500 hover:text-slate-700">
        Sources ({cards.length})
      </summary>
      <ol className="mt-2 space-y-1 pl-1">
        {cards.map((card) => (
          <li key={card.handle} className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-slate-800">{card.source_title}</span>
            <Badge tone="neutral">{card.source_class}</Badge>
            <span>{card.locator_label}</span>
            <Link
              href={evidenceViewerHref(ws, card.handle, card.anchor_child_id)}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all font-mono text-indigo-700 hover:underline"
            >
              {card.handle}
            </Link>
          </li>
        ))}
      </ol>
    </details>
  );
}

export interface AnswerViewProps {
  ws: string;
  content: string;
  citations: readonly AnyCitationCard[];
  sections: unknown;
}

/** Verified answer renderer, shared by the live `final` event and stored assistant messages. */
export function AnswerView({ ws, content, citations, sections }: AnswerViewProps) {
  const parsed = useMemo(() => parseSections(sections), [sections]);
  const ctx = useMemo<CitationContext>(() => ({ cards: citations }), [citations]);
  const unknowns = useMemo(
    () => new Set(parsed.kind === "generated" ? parsed.answerUnknowns.map((u) => u.trim()) : []),
    [parsed],
  );

  let body: ReactNode;
  if (parsed.kind === "evidence_only") {
    body = (
      <>
        <Banner tone="amber">No verified answer — showing the most relevant evidence</Banner>
        {parsed.reason && (
          <p className="text-xs text-slate-500">
            Reason: <code className="font-mono">{humanize(parsed.reason)}</code>
          </p>
        )}
        <ul className="grid gap-2">
          {parsed.units.map((unit, i) => (
            <li key={i} className="rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm">
              <SafeMarkdown inline text={unit} ws={ws} citations={ctx} />
            </li>
          ))}
        </ul>
      </>
    );
  } else if (parsed.kind === "abstained") {
    body = (
      <>
        <Banner tone="slate">Insufficient evidence in this workspace</Banner>
        {parsed.answer.length > 0 && (
          <p className="text-sm text-slate-700">
            {parsed.answer.map((unit, i) => (
              <span key={i}>
                <SafeMarkdown inline text={stripInference(unit).text} ws={ws} />{" "}
              </span>
            ))}
          </p>
        )}
        {parsed.gaps.length > 0 && <GapsPanel units={parsed.gaps} ws={ws} />}
      </>
    );
  } else if (parsed.kind === "generated") {
    body = (
      <>
        {parsed.answer.length > 0 && (
          <SectionBlock title="Answer" tone="evidence" hint="evidence-backed; inferences labelled">
            <p className="leading-relaxed">
              {parsed.answer.map((unit, i) => (
                <span key={i}>
                  <AnswerUnit unit={unit} ws={ws} citations={ctx} unknowns={unknowns} />{" "}
                </span>
              ))}
            </p>
          </SectionBlock>
        )}
        {parsed.findings.length > 0 && (
          <SectionBlock title="Key findings" tone="evidence" hint="Evidence">
            <UnitList units={parsed.findings} ws={ws} citations={ctx} />
          </SectionBlock>
        )}
        {parsed.conflicts.length > 0 && (
          <SectionBlock title="Conflicting evidence" tone="conflict">
            <UnitList units={parsed.conflicts} ws={ws} citations={ctx} />
          </SectionBlock>
        )}
        {parsed.interpretation.length > 0 && (
          <SectionBlock title="Interpretation" tone="inference" hint="Inference — not stated in the evidence">
            <UnitList units={parsed.interpretation} ws={ws} citations={ctx} />
          </SectionBlock>
        )}
        {parsed.gaps.length > 0 && <GapsPanel units={parsed.gaps} ws={ws} />}
      </>
    );
  } else {
    body = <SafeMarkdown text={content} ws={ws} citations={ctx} />;
  }

  return (
    <div className="flex flex-col gap-3">
      {body}
      <SourceList ws={ws} cards={citations} />
    </div>
  );
}

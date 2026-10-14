"use client";

import { Presentation } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, LinkButton } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, Input, Textarea } from "@/components/ui/form-controls";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, LoadingRegion } from "@/components/ui/states";
import { useAnalyses, useInsights } from "@/lib/api/hooks/insights";
import { analyticsHref, insightsHref, opportunitiesHref } from "@/lib/routes";
import { DeckDownload } from "./deck-download";
import { DeckGenerating } from "./deck-generating";
import { DeckOutline } from "./deck-outline";
import { DeckPicker } from "./deck-picker";
import { DeckPreview, ExcludedList } from "./deck-preview";
import {
  DEFAULT_DECK_TITLE,
  deckErrorMessage,
  deckRequest,
  exclusionViews,
  knownIds,
  pickerGroups,
  pickHref,
  pickSize,
  QUESTION_MAX,
  QUESTION_PLACEHOLDER,
  selectedGroups,
  TITLE_MAX,
  togglePick,
  unknownPicks,
  withoutUnknown,
  type DeckPick,
  type PickerGroup,
  type PickKind,
} from "./deck-view";
import { useDeckGeneration, useOutlinePreview } from "./use-deck-generation";

export const DECK_DESCRIPTION =
  "Turn verified findings into a concise, cited deck. Every slide is built only from the findings you select.";
export const EMPTY_SELECTION = "Select findings from Insights, Growth Opportunities or Analytics to build a presentation.";

/** Teaching empty state for an empty selection, with the three places findings come from. */
export function EmptySelection({ ws, onChoose }: { ws: string; onChoose?: () => void }) {
  return (
    <EmptyState
      icon={Presentation}
      size="sm"
      title="No findings selected yet"
      description={EMPTY_SELECTION}
      action={
        <div className="flex flex-wrap justify-center gap-2">
          {onChoose && <Button onClick={onChoose}>Choose findings here</Button>}
          <LinkButton href={insightsHref(ws)} variant="ghost">
            Insights
          </LinkButton>
          <LinkButton href={opportunitiesHref(ws)} variant="ghost">
            Growth Opportunities
          </LinkButton>
          <LinkButton href={analyticsHref(ws)} variant="ghost">
            Analytics
          </LinkButton>
        </div>
      }
    />
  );
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function Selection({
  ws,
  groups,
  pick,
  onToggle,
}: {
  ws: string;
  groups: readonly PickerGroup[];
  pick: DeckPick;
  onToggle: (kind: PickKind, id: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const chosen = selectedGroups(groups, pick);
  const count = chosen.reduce((n, g) => n + g.items.length, 0);
  if (groups.length === 0) {
    return <EmptySelection ws={ws} />;
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm tabular-nums text-secondary">{count === 0 ? "Nothing selected" : `${plural(count, "finding")} selected`}</p>
        {count > 0 && (
          <Button variant="quiet" size="sm" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Show selected only" : "Add more findings"}
          </Button>
        )}
      </div>
      {count === 0 && !showAll ? (
        <EmptySelection ws={ws} onChoose={() => setShowAll(true)} />
      ) : (
        <DeckPicker groups={showAll ? groups : chosen} pick={pick} onToggle={onToggle} />
      )}
    </div>
  );
}

function OutlinePanel({
  ws,
  body,
  empty,
  groups,
}: {
  ws: string;
  body: ReturnType<typeof deckRequest> | null;
  empty: boolean;
  groups: readonly PickerGroup[];
}) {
  const preview = useOutlinePreview(ws, body);
  if (empty) return <p className="text-sm text-muted">The outline appears once you select findings.</p>;
  if (body && preview.isError && !preview.isFetching && !preview.settling) {
    return <p className="text-sm text-danger">{deckErrorMessage(preview.error)}</p>;
  }
  if (!body || !preview.data) return <LoadingRegion label="Composing the outline" lines={6} />;
  return (
    <div className={preview.isFetching || preview.settling ? "opacity-60 transition-opacity duration-(--duration-base)" : undefined} aria-busy={preview.isFetching || undefined}>
      <DeckOutline deck={preview.data.deck} />
      <div className="mt-4">
        <ExcludedList items={exclusionViews(preview.data.deck.excluded, groups)} />
      </div>
    </div>
  );
}

type Step = "compose" | "generate";

/** Create presentation: compose (details + selection + live outline), generate, preview + export. */
export function DeckBuilder({ ws, initial }: { ws: string; initial: DeckPick }) {
  const brief = useInsights(ws);
  const analyses = useAnalyses(ws);
  const [pick, setPick] = useState<DeckPick>(initial);
  const [title, setTitle] = useState(DEFAULT_DECK_TITLE);
  const [question, setQuestion] = useState("");
  const [step, setStep] = useState<Step>("compose");
  const generation = useDeckGeneration(ws);
  const [generatedBody, setGeneratedBody] = useState<ReturnType<typeof deckRequest> | null>(null);

  const loading = brief.isPending || analyses.isPending;
  const groups = useMemo(() => pickerGroups(brief.data, analyses.data?.analyses), [brief.data, analyses.data]);
  const known = useMemo(() => knownIds(brief.data, analyses.data?.analyses), [brief.data, analyses.data]);
  const ready = !loading && !brief.isError && !analyses.isError;
  const usable = ready ? withoutUnknown(pick, known) : pick;
  const stale = ready ? pickSize(unknownPicks(pick, known)) : 0;
  const body = !loading && pickSize(usable) > 0 ? deckRequest(usable, title, question) : null;

  // Keep the URL in step with the selection so the page can be shared or reloaded.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    window.history.replaceState(null, "", pickHref(ws, pick));
  }, [ws, pick]);

  // The preview shows once the deck is composed and the file request has settled.
  const settled = generation.deck !== null && (generation.phase === "done" || generation.phase === "failed");
  const view: "compose" | "generating" | "preview" = step === "compose" ? "compose" : settled ? "preview" : "generating";

  const generate = () => {
    if (!body) return;
    setGeneratedBody(body);
    setStep("generate");
    generation.start(body);
  };
  const backToCompose = () => {
    generation.cancel();
    setStep("compose");
  };

  if (view === "generating") {
    return (
      <PageContainer>
        <DeckGenerating
          title={title.trim() || DEFAULT_DECK_TITLE}
          stages={generation.stages}
          phase={generation.phase}
          error={generation.error}
          onCancel={backToCompose}
          onRetry={generate}
        />
      </PageContainer>
    );
  }

  if (view === "preview" && generation.deck && generatedBody) {
    const deck = generation.deck;
    return (
      <PageContainer width="wide">
        <div className="ms-page-enter flex flex-col gap-6">
          <PageHeader
            breadcrumb={[{ label: "Insights", href: insightsHref(ws) }]}
            title={deck.title}
            description={deck.question ?? DECK_DESCRIPTION}
            meta={`${plural(deck.counts.slides, "slide")} · ${plural(deck.counts.items, "finding")} · ${plural(deck.counts.sources, "source")}`}
            actions={
              <div className="flex flex-wrap items-start gap-2">
                <Button variant="ghost" onClick={backToCompose}>
                  Edit selection
                </Button>
                <DeckDownload ws={ws} body={generatedBody} initial={generation.file} />
              </div>
            }
          />
          <ExcludedList items={exclusionViews(deck.excluded, groups)} />
          <DeckPreview deck={deck} />
        </div>
      </PageContainer>
    );
  }

  const onToggle = (kind: PickKind, id: string) => setPick((p) => togglePick(p, kind, id));
  return (
    <PageContainer width="wide">
      <div className="ms-page-enter flex flex-col gap-6">
        <PageHeader breadcrumb={[{ label: "Insights", href: insightsHref(ws) }]} title="Create presentation" description={DECK_DESCRIPTION} />
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex min-w-0 flex-col gap-8">
            <section aria-labelledby="deck-details" className="flex flex-col gap-4">
              <h2 id="deck-details" className="text-md font-semibold text-primary">
                Presentation details
              </h2>
              <Field id="deck-title" label="Title">
                <Input id="deck-title" value={title} maxLength={TITLE_MAX} onChange={(e) => setTitle(e.target.value)} />
              </Field>
              <Field id="deck-question" label="Strategic question" hint="Optional. Shown on the title slide.">
                <Textarea
                  id="deck-question"
                  rows={2}
                  value={question}
                  maxLength={QUESTION_MAX}
                  placeholder={`e.g. ${QUESTION_PLACEHOLDER}`}
                  onChange={(e) => setQuestion(e.target.value)}
                />
              </Field>
            </section>
            <section aria-labelledby="deck-findings" className="flex flex-col gap-3">
              <h2 id="deck-findings" className="text-md font-semibold text-primary">
                Findings
              </h2>
              {stale > 0 && (
                <Callout tone="warn" title={`${plural(stale, "selected finding")} ${stale === 1 ? "is" : "are"} no longer in this workspace`}>
                  {stale === 1 ? "It was" : "They were"} left out of the presentation.
                </Callout>
              )}
              {loading ? (
                <LoadingRegion label="Loading findings" lines={6} />
              ) : brief.isError || analyses.isError ? (
                <ErrorState
                  title="Findings could not be loaded"
                  error={brief.error ?? analyses.error}
                  retry={() => {
                    void brief.refetch();
                    void analyses.refetch();
                  }}
                />
              ) : (
                <Selection ws={ws} groups={groups} pick={pick} onToggle={onToggle} />
              )}
            </section>
          </div>
          <aside aria-labelledby="deck-outline" className="flex flex-col gap-4 lg:sticky lg:top-6">
            <h2 id="deck-outline" className="text-md font-semibold text-primary">
              Outline
            </h2>
            <OutlinePanel ws={ws} body={body} empty={pickSize(usable) === 0} groups={groups} />
            <Button disabled={!body} onClick={generate} className="w-full">
              Generate presentation
            </Button>
            <p className="text-xs text-muted">Creates the slides and saves a PowerPoint file. Claims keep their labels and source numbers.</p>
          </aside>
        </div>
      </div>
    </PageContainer>
  );
}

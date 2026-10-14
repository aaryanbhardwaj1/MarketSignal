import { SignalLoader } from "@/components/motion/signal-loader";
import { StageProgress, type Stage } from "@/components/motion/stage-progress";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import type { GenerationPhase } from "./generation";

/** Generation view: honest stages driven by the compose and file requests. */
export function DeckGenerating({
  title,
  stages,
  phase,
  error,
  onCancel,
  onRetry,
}: {
  title: string;
  stages: Stage[];
  phase: GenerationPhase;
  error: string | null;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const failed = phase === "failed";
  return (
    <section aria-labelledby="deck-generating" className="ms-fade-in mx-auto flex w-full max-w-md flex-col gap-6 py-10">
      <div className="flex flex-col gap-2">
        {!failed && <SignalLoader size="lg" label="Generating presentation" />}
        <h2 id="deck-generating" className="text-lg font-semibold text-primary">
          {failed ? "The presentation could not be generated" : "Generating presentation"}
        </h2>
        <p className="text-sm text-secondary">{title}</p>
      </div>
      <StageProgress stages={stages} label="Presentation generation" />
      {failed && error && <Callout tone="danger" title="Nothing was created">{error}</Callout>}
      <div className="flex gap-2">
        {failed ? (
          <>
            <Button onClick={onRetry}>Try again</Button>
            <Button variant="ghost" onClick={onCancel}>
              Back to selection
            </Button>
          </>
        ) : (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </section>
  );
}

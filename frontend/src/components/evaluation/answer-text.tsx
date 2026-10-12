import { Fragment, type ReactNode } from "react";
import { parseAnswer, parseHandle, splitInline, type AnswerPart } from "@/lib/eval-view";

/** Non-interactive citation label: the source code and locator of the cited evidence passage. */
export function HandleChip({ handle, marked = false }: { handle: string; marked?: boolean }) {
  const { source, locator } = parseHandle(handle);
  return (
    <span
      title={handle}
      className={
        marked
          ? "mx-0.5 inline-flex items-center gap-1 rounded-sm border border-cite-evidence/50 bg-cite-evidence-bg px-1 align-baseline font-mono text-xs text-cite-evidence"
          : "mx-0.5 inline-flex items-center gap-1 rounded-sm border border-border bg-surface-muted px-1 align-baseline font-mono text-xs text-secondary"
      }
    >
      {source}
      {locator && <span className="opacity-80">· {locator}</span>}
    </span>
  );
}

function Parts({ parts }: { parts: AnswerPart[] }) {
  return (
    <>
      {parts.map((p, i) => (
        <Fragment key={i}>
          {p.kind === "text" ? (
            p.text
          ) : p.kind === "cite" ? (
            <HandleChip handle={p.handle} marked />
          ) : (
            <span className="mx-0.5 inline-flex items-center rounded-sm border border-dashed border-border-strong px-1 align-baseline text-xs text-cite-inference">
              Inference
            </span>
          )}
        </Fragment>
      ))}
    </>
  );
}

/** One stored sentence or note with any citation markers shown as source labels. */
export function InlineText({ text }: { text: string }) {
  return <Parts parts={splitInline(text)} />;
}

/**
 * Stored final answer as recorded by the eval harness. Rendered as React text only (no HTML),
 * with citation markers shown as source-code labels that do not open anything.
 */
export function AnswerText({ markdown }: { markdown: string }) {
  const blocks = parseAnswer(markdown);
  if (blocks.length === 0) return <p className="text-base text-muted">No answer text was stored for this item.</p>;
  const out: ReactNode[] = [];
  let bullets: AnswerPart[][] = [];
  const flush = (key: string) => {
    if (bullets.length) {
      out.push(
        <ul key={key} className="my-1.5 flex list-disc flex-col gap-1 pl-5">
          {bullets.map((b, i) => (
            <li key={i}>
              <Parts parts={b} />
            </li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };
  blocks.forEach((b, i) => {
    if (b.kind === "bullet") {
      bullets.push(b.parts);
      return;
    }
    flush(`ul-${i}`);
    out.push(
      b.kind === "heading" ? (
        <h4 key={i} className="mt-3 text-sm font-semibold text-primary first:mt-0">
          <Parts parts={b.parts} />
        </h4>
      ) : (
        <p key={i} className="my-1.5">
          <Parts parts={b.parts} />
        </p>
      ),
    );
  });
  flush("ul-end");
  return <div className="text-base leading-relaxed text-primary">{out}</div>;
}

import type { ReactNode } from "react";
import { HBarChart } from "@/components/charts/hbar-chart";
import { ClaimTag } from "@/components/ui/claim-tag";
import { isEvidenceStatus, StatusPill } from "@/components/ui/status-pill";
import type { ClaimType, DeckBlock, DeckBullet, DeckSlide } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { SECTION_LABEL } from "./deck-view";

/** Numbered citation markers pointing at the sources appendix. */
export function Cites({ cites }: { cites: readonly number[] }) {
  if (cites.length === 0) return null;
  return (
    <span className="ml-1 inline-flex gap-0.5 align-super text-2xs font-medium leading-none text-accent-text">
      <span className="sr-only">Sources </span>
      {cites.map((n, i) => (
        <span key={n} className="tabular-nums">
          [{n}]{i < cites.length - 1 && <span className="sr-only">, </span>}
        </span>
      ))}
    </span>
  );
}

/** Visible claim tag for interpretive claims only; facts (observed, derived) carry none, as in the file. */
function Label({ claim, label }: { claim: ClaimType | null; label: string | null }) {
  if (!label || !claim) return null;
  return <ClaimTag type={claim} size="sm" className="mr-1.5" />;
}

function Bullets({ items }: { items: readonly DeckBullet[] }) {
  return (
    <ul className="flex flex-col gap-2.5">
      {items.map((b, i) => (
        <li key={i} className={cx("flex gap-2 text-base leading-snug text-primary", b.level === 1 && "ml-6 text-sm text-secondary")}>
          <span aria-hidden className={cx("mt-2 h-1 w-1 shrink-0 rounded-full", b.level === 1 ? "bg-border-strong" : "bg-accent")} />
          <span className="min-w-0">
            <Label claim={b.claim_type} label={b.label} />
            {b.heading && <span className="font-semibold">{b.heading}: </span>}
            {b.text}
            <Cites cites={b.cites} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function Base({ text }: { text: string | null }) {
  return text ? <p className="mt-1 text-xs text-muted">{text}</p> : null;
}

function Block({ block }: { block: DeckBlock }) {
  switch (block.type) {
    case "bullets":
      return <Bullets items={block.items} />;
    case "statuses":
      return (
        <ul className="divide-y divide-border border-y border-border">
          {block.items.map((row, i) => (
            <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
              <span className="min-w-0 flex-1 text-base font-medium text-primary">
                <Label claim={row.claim_type} label={row.label} />
                {row.title}
                <Cites cites={row.cites} />
              </span>
              <span className="text-xs text-muted">{row.kind_label}</span>
              {row.status && isEvidenceStatus(row.status) ? (
                <StatusPill status={row.status} />
              ) : (
                row.status_label && <span className="text-xs text-secondary">{row.status_label}</span>
              )}
            </li>
          ))}
        </ul>
      );
    case "metrics":
      return (
        <dl className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3">
          {block.items.map((m, i) => (
            <div key={i} className="flex flex-col-reverse">
              <dt className="text-sm text-secondary">
                {m.label}
                <Cites cites={m.cites} />
                <Base text={m.base} />
              </dt>
              <dd className="text-display font-semibold tabular-nums text-primary">{m.display}</dd>
            </div>
          ))}
        </dl>
      );
    case "sources":
      return block.items.length === 0 ? (
        <p className="text-sm text-muted">No sources were cited in this presentation.</p>
      ) : (
        <ol className="flex flex-col gap-2.5">
          {block.items.map((s) => (
            <li key={s.n} className="flex gap-3 text-sm">
              <span className="w-6 shrink-0 text-right font-medium tabular-nums text-accent-text">[{s.n}]</span>
              <span className="min-w-0">
                <span className="font-medium text-primary">{s.source_title}</span>
                <span className="text-muted"> · {s.locator}</span>
                {s.quote && <span className="mt-0.5 block italic text-secondary">&ldquo;{s.quote}&rdquo;</span>}
              </span>
            </li>
          ))}
        </ol>
      );
    case "chart": {
      const display = new Map(block.values.map((v, i) => [v, block.displays[i] ?? String(v)]));
      return (
        <div>
          <HBarChart
            data={block.categories.map((label, i) => ({ label, value: block.values[i] ?? 0, emphasis: i === block.emphasis }))}
            ariaLabel={block.title}
            title={
              <>
                {block.title}
                <Cites cites={block.cites} />
              </>
            }
            caption={block.base ?? undefined}
            format={(v) => display.get(v) ?? String(v)}
          />
        </div>
      );
    }
    case "table":
      return (
        <figure>
          <figcaption className="mb-2 text-sm font-semibold text-primary">
            {block.title}
            <Cites cites={block.cites} />
          </figcaption>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-strong text-left text-xs text-muted">
                {block.columns.map((c) => (
                  <th key={c} scope="col" className="py-1.5 pr-4 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r} className="border-b border-border">
                  {row.map((cell, c) => (
                    <td key={c} className="py-1.5 pr-4 tabular-nums text-primary">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {(block.note || block.truncated) && <p className="mt-1.5 text-xs text-muted">{block.note ?? "Showing the first rows only."}</p>}
          <Base text={block.base} />
        </figure>
      );
  }
}

function TitleSlide({ slide }: { slide: DeckSlide }) {
  return (
    <div className="flex h-full flex-col justify-center gap-4">
      <span aria-hidden className="h-1 w-12 rounded-full bg-accent" />
      <h3 className="text-display font-semibold text-primary">{slide.title}</h3>
      {slide.subtitle && <p className="max-w-[40ch] text-lg text-secondary">{slide.subtitle}</p>}
      {slide.meta && slide.meta.length > 0 && <p className="text-sm text-muted">{slide.meta.join(" · ")}</p>}
    </div>
  );
}

/** One slide as a 16:9 frame, rendered from the preview JSON (what the .pptx contains). */
export function DeckSlideFrame({ slide, total, footer }: { slide: DeckSlide; total: number; footer?: ReactNode }) {
  return (
    <article
      aria-label={`Slide ${slide.index} of ${total}: ${slide.title}`}
      className="relative flex aspect-video w-full flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-raised"
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-auto px-[5%] pb-10 pt-[4%]">
        {slide.kind === "title" ? (
          <TitleSlide slide={slide} />
        ) : (
          <>
            <p className="text-xs font-medium text-accent-text">{slide.subtitle ?? SECTION_LABEL[slide.kind]}</p>
            <h3 className="mt-1 text-xl font-semibold text-primary">{slide.title}</h3>
            <div className="mt-5 flex flex-col gap-6">
              {slide.blocks.map((block, i) => (
                <Block key={i} block={block} />
              ))}
            </div>
          </>
        )}
      </div>
      <div className="absolute inset-x-[5%] bottom-3 flex items-center justify-between text-2xs text-muted">
        <span>{footer}</span>
        <span className="tabular-nums">{slide.index}</span>
      </div>
    </article>
  );
}

/** Small schematic of a slide for the thumbnail rail (title + block shapes, not real content). */
export function DeckSlideThumb({ slide }: { slide: DeckSlide }) {
  return (
    <span aria-hidden className="flex aspect-video w-full flex-col gap-1 overflow-hidden rounded-md border border-border bg-surface p-2 text-left">
      <span className={cx("line-clamp-2 font-medium leading-tight text-primary", slide.kind === "title" && "mt-auto", "text-2xs")}>
        {slide.title}
      </span>
      {slide.kind !== "title" &&
        slide.blocks.slice(0, 2).map((b, i) => (
          <span key={i} className="flex flex-col gap-0.5">
            {b.type === "chart" || b.type === "metrics" ? (
              <span className="h-2 w-2/3 rounded-sm bg-accent-muted" />
            ) : (
              <>
                <span className="h-0.5 w-11/12 rounded-full bg-border-strong" />
                <span className="h-0.5 w-3/4 rounded-full bg-border-strong" />
              </>
            )}
          </span>
        ))}
    </span>
  );
}

import { BrandLockup, BrandMark, BrandMotif } from "@/components/brand/brand-mark";
import { Block, GallerySection, Grid } from "./gallery-parts";

const SWATCH_GROUPS: Array<[string, string[]]> = [
  ["Surfaces and lines", ["canvas", "surface", "raised", "sunken", "surface-muted", "border", "border-strong", "border-control"]],
  ["Ink", ["ink", "text-secondary", "text-muted", "text-disabled"]],
  ["Accent", ["accent", "accent-hover", "accent-text", "accent-muted", "accent-subtle"]],
  ["Semantic", ["success", "warn", "danger", "info", "neutral"]],
  [
    "Claim types",
    ["claim-observed", "claim-derived", "claim-inference", "claim-hypothesis", "claim-observed-bg", "claim-derived-bg", "claim-inference-bg", "claim-hypothesis-bg"],
  ],
  [
    "Statuses",
    ["status-strong", "status-supported", "status-emerging", "status-mixed", "status-validation", "status-strong-bg", "status-supported-bg", "status-mixed-bg"],
  ],
  ["Chart", ["chart-1", "chart-2", "chart-3", "chart-4", "chart-grid", "chart-axis", "chart-reference", "chart-negative"]],
];

const TYPE_SCALE: Array<[string, string, string]> = [
  ["text-display", "30 / 36", "Hero figure 1,284"],
  ["text-xl", "24 / 28", "Page title"],
  ["text-lg", "18 / 26", "Panel title"],
  ["text-md", "15 / 22", "Section heading"],
  ["text-base", "14 / 22", "Body copy for reading"],
  ["text-sm", "13 / 20", "Secondary and meta text"],
  ["text-xs", "12 / 16", "Labels and captions"],
  ["text-2xs", "11 / 14", "Citation numerals"],
];

function Swatch({ name }: { name: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span aria-hidden className="h-8 w-8 shrink-0 rounded-md border border-border" style={{ background: `var(--color-${name})` }} />
      <span className="min-w-0 truncate font-mono text-xs text-secondary">{name}</span>
    </div>
  );
}

export function FoundationsSection() {
  return (
    <>
      <GallerySection id="tokens" title="Tokens" description="Cool neutrals, one signal-blue accent, semantic, claim-type, status and chart tones.">
        <div className="grid gap-x-6 gap-y-8 md:grid-cols-2 xl:grid-cols-3">
          {SWATCH_GROUPS.map(([group, names]) => (
            <Block key={group} title={group}>
              <div className="grid grid-cols-2 gap-2.5">
                {names.map((n) => (
                  <Swatch key={n} name={n} />
                ))}
              </div>
            </Block>
          ))}
          <Block title="Radii and depth">
            <div className="flex flex-wrap items-end gap-4">
              <span className="flex h-14 w-20 items-end rounded-md border border-border bg-surface p-1.5 text-2xs text-muted">md 6</span>
              <span className="flex h-14 w-20 items-end rounded-lg border border-border bg-raised p-1.5 text-2xs text-muted shadow-raised">lg 8 raised</span>
              <span className="flex h-14 w-20 items-end rounded-float border border-border bg-surface p-1.5 text-2xs text-muted shadow-overlay">float 12</span>
            </div>
          </Block>
        </div>
      </GallerySection>

      <GallerySection id="type" title="Type scale" description="Geist Sans; Geist Mono only for identifiers, logs and code. Tabular numerals on every metric.">
        <dl className="divide-y divide-border">
          {TYPE_SCALE.map(([cls, size, sample]) => (
            <div key={cls} className="flex items-baseline gap-6 py-2.5">
              <dt className="w-28 shrink-0 font-mono text-xs text-muted">{cls}</dt>
              <dd className="w-16 shrink-0 text-xs tabular-nums text-muted">{size}</dd>
              <dd className={`${cls} min-w-0 truncate font-semibold text-primary tabular-nums`}>{sample}</dd>
            </div>
          ))}
          <div className="flex items-baseline gap-6 py-2.5">
            <dt className="w-28 shrink-0 font-mono text-xs text-muted">font-mono</dt>
            <dd className="w-16 shrink-0 text-xs text-muted">12 / 16</dd>
            <dd className="font-mono text-xs text-secondary">SAMPLE/SOURCE@v1:P1</dd>
          </div>
        </dl>
      </GallerySection>

      <GallerySection id="brand" title="Brand" description="Mark, wordmark lockup at the sizes the product uses, and the quiet motif.">
        <Grid cols={4}>
          <Block title="Lockup 18 / 22 / 28">
            <div className="flex flex-col gap-3">
              <BrandLockup size={18} />
              <BrandLockup size={22} />
              <BrandLockup size={28} />
            </div>
          </Block>
          <Block title="Mark only 16 / 24 / 40">
            <div className="flex items-end gap-4">
              <BrandMark size={16} />
              <BrandMark size={24} />
              <BrandMark size={40} />
            </div>
          </Block>
          <Block title="Rail (mark only lockup)">
            <BrandLockup hideWordmark />
          </Block>
          <Block title="Motif">
            <div className="relative h-14 overflow-hidden rounded-md border border-border bg-surface">
              <BrandMotif />
            </div>
          </Block>
        </Grid>
      </GallerySection>
    </>
  );
}

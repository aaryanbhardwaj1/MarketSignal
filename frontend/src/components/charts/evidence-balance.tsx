import type { ReactNode } from "react";
import { ChartFrame } from "./chart-frame";
import { stackShares } from "./scale";

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * Supporting vs contradicting evidence as one split bar with counts on both ends (and an
 * optional neutral/context middle). Counts are always printed; colour is secondary.
 */
export function EvidenceBalance({
  supporting,
  contradicting,
  neutral = 0,
  labels = { supporting: "Supporting", contradicting: "Contradicting", neutral: "Context" },
  caption,
  className,
}: {
  supporting: number;
  contradicting: number;
  neutral?: number;
  labels?: { supporting: string; contradicting: string; neutral?: string };
  caption?: ReactNode;
  className?: string;
}) {
  const [sup, neu, con] = stackShares([supporting, neutral, contradicting]);
  const total = supporting + contradicting + neutral;
  const ariaLabel = `${labels.supporting}: ${plural(supporting, "source")}; ${labels.contradicting}: ${plural(contradicting, "source")}${neutral ? `; ${labels.neutral ?? "Context"}: ${neutral}` : ""}`;
  const table = {
    columns: ["Evidence", "Sources"],
    rows: [[labels.supporting, supporting], ...(neutral ? [[labels.neutral ?? "Context", neutral]] : []), [labels.contradicting, contradicting]],
  };
  return (
    <ChartFrame ariaLabel={ariaLabel} table={table} caption={caption} className={className}>
      <div aria-hidden className="flex items-baseline justify-between text-xs">
        <span className="text-secondary">
          {labels.supporting} <span className="font-semibold text-primary">{supporting}</span>
        </span>
        <span className={contradicting > 0 ? "text-contradicting" : "text-secondary"}>
          <span className="font-semibold">{contradicting}</span> {labels.contradicting}
        </span>
      </div>
      <div aria-hidden className="mt-1.5 flex h-2 w-full gap-0.5 overflow-hidden rounded-full bg-sunken">
        {total > 0 && (
          <>
            {sup.share > 0 && <span className="h-full rounded-l-full bg-accent" style={{ width: `${sup.share * 100}%` }} />}
            {neu.share > 0 && <span className="h-full" style={{ width: `${neu.share * 100}%`, backgroundColor: "var(--color-chart-3)" }} />}
            {con.share > 0 && <span className="h-full rounded-r-full" style={{ width: `${con.share * 100}%`, backgroundColor: "var(--color-contradicting)" }} />}
          </>
        )}
      </div>
    </ChartFrame>
  );
}

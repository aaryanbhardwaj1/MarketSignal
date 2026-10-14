"use client";

import { Presentation } from "lucide-react";
import { Button, LinkButton } from "@/components/ui/button";
import { formatCount } from "@/lib/format";

/** Sticky footer while findings are selected: the count, a clear action and a way to reset. */
export function SelectionBar({ count, href, onClear }: { count: number; href: string; onClear: () => void }) {
  if (count === 0) return null;
  return (
    <div className="sticky bottom-4 z-10 mt-6 flex justify-center ms-pop-in" role="region" aria-label="Presentation selection">
      <div className="flex items-center gap-3 rounded-float border border-border bg-raised py-2 pl-4 pr-2 shadow-overlay">
        <p className="text-sm text-primary tabular-nums" aria-live="polite">
          {formatCount(count, "finding")} selected
        </p>
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
        <LinkButton href={href} variant="primary" size="sm" iconLeft={<Presentation aria-hidden size={14} />}>
          Create presentation
        </LinkButton>
      </div>
    </div>
  );
}

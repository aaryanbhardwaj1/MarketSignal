"use client";

import { ClaimTag } from "@/components/ui/claim-tag";
import { isEvidenceStatus, StatusPill } from "@/components/ui/status-pill";
import { cx } from "@/lib/cx";
import { canAdd, isPicked, type DeckPick, type PickerGroup, type PickerItem, type PickKind } from "./deck-view";

const LIMIT_HINT = "Limit reached for this kind of finding";

function Row({ item, pick, onToggle }: { item: PickerItem; pick: DeckPick; onToggle: (kind: PickKind, id: string) => void }) {
  const checked = isPicked(pick, item.kind, item.id);
  const disabled = !checked && !canAdd(pick, item.kind);
  const id = `deck-pick-${item.kind}-${item.id}`;
  return (
    <li className={cx("flex items-start gap-3 py-2", disabled && "opacity-60")}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        title={disabled ? LIMIT_HINT : undefined}
        onChange={() => onToggle(item.kind, item.id)}
        className="mt-0.5 h-4 w-4 shrink-0 rounded-sm accent-accent"
      />
      <label htmlFor={id} className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
        <span className="min-w-0 text-base text-primary">{item.title}</span>
        {item.status && isEvidenceStatus(item.status) && <StatusPill status={item.status} />}
        {item.claim && <ClaimTag type={item.claim} size="sm" />}
        {item.hint && <span className="text-xs text-muted">{item.hint}</span>}
      </label>
    </li>
  );
}

/** Grouped checklist of findings (opportunities, insights by category, analyses). */
export function DeckPicker({
  groups,
  pick,
  onToggle,
}: {
  groups: readonly PickerGroup[];
  pick: DeckPick;
  onToggle: (kind: PickKind, id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-5">
      {groups.map((group) => {
        const selected = group.items.filter((i) => isPicked(pick, i.kind, i.id)).length;
        return (
          <fieldset key={group.id} className="min-w-0">
            <legend className="flex w-full items-baseline justify-between gap-3 border-b border-border pb-1.5 text-sm font-semibold text-primary">
              {group.label}
              <span className="text-xs font-normal tabular-nums text-muted">
                {selected} of {group.items.length} selected
              </span>
            </legend>
            <ul className="divide-y divide-border">
              {group.items.map((item) => (
                <Row key={`${item.kind}:${item.id}`} item={item} pick={pick} onToggle={onToggle} />
              ))}
            </ul>
          </fieldset>
        );
      })}
    </div>
  );
}

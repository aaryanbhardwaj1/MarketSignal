"use client";

import { useId } from "react";
import { cx } from "@/lib/cx";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  /** Id of an element that describes this option (announced with it by screen readers). */
  describedBy?: string;
}

/**
 * Segmented control: a radio group styled as joined buttons. Built on native radio inputs, so
 * Arrow keys move the selection and Tab enters/leaves the group like any radio group.
 *
 * `label` names the group for assistive tech (fieldset legend). `visibleLabel` is the short
 * caption shown beside the control (defaults to `label`); pass `null` to show none.
 */
export function Segmented<T extends string>({
  label,
  visibleLabel,
  value,
  options,
  onChange,
  disabled = false,
  name,
}: {
  label: string;
  visibleLabel?: string | null;
  value: T;
  options: readonly SegmentedOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  /** Radio group name; defaults to a unique id. */
  name?: string;
}) {
  const autoName = useId();
  const groupName = name ?? `${autoName}-segmented`;
  const caption = visibleLabel === undefined ? label : visibleLabel;
  return (
    <fieldset className="flex min-w-0 flex-wrap items-center gap-2" disabled={disabled}>
      <legend className="sr-only">{label}</legend>
      {caption && (
        <span aria-hidden className="text-sm text-muted">
          {caption}
        </span>
      )}
      <div className="inline-flex rounded-md border border-border bg-surface-muted p-0.5">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <label
              key={option.value}
              className={cx(
                "relative cursor-pointer rounded-sm px-2.5 py-1 text-sm font-medium transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent",
                selected ? "bg-surface text-primary shadow-sm" : "text-secondary hover:text-primary",
              )}
            >
              <input
                type="radio"
                name={groupName}
                value={option.value}
                checked={selected}
                onChange={() => onChange(option.value)}
                aria-describedby={option.describedBy}
                className="sr-only"
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

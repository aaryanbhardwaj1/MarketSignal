import type { ReactNode } from "react";
import { Button } from "./button";
import { Select, type SelectOption } from "./form-controls";

/** Horizontal row of filters with an optional reset. */
export function FilterBar({ children, onReset }: { children: ReactNode; onReset?: () => void }) {
  return (
    <div role="group" aria-label="Filters" className="flex flex-wrap items-end gap-3">
      {children}
      {onReset && (
        <Button variant="ghost" size="sm" onClick={onReset} className="mb-1">
          Reset filters
        </Button>
      )}
    </div>
  );
}

export function FilterSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex min-w-40 flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-secondary">
        {label}
      </label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} options={options} controlSize="sm" />
    </div>
  );
}

/** Removable chips for the filters currently applied. */
export function ActiveFilters({ items }: { items: { label: string; onRemove: () => void }[] }) {
  if (items.length === 0) return null;
  return (
    <ul aria-label="Active filters" className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item.label}>
          <button
            type="button"
            onClick={item.onRemove}
            aria-label={`Remove filter: ${item.label}`}
            className="inline-flex items-center gap-1 rounded-sm border border-border bg-surface-muted px-2 py-0.5 text-sm text-primary hover:border-border-strong"
          >
            {item.label}
            <span aria-hidden className="text-muted">
              ×
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

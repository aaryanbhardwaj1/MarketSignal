import { X } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./button";
import { Select, type SelectOption } from "./form-controls";

/** Horizontal row of filters with an optional reset. */
export function FilterBar({ children, onReset }: { children: ReactNode; onReset?: () => void }) {
  return (
    <div role="group" aria-label="Filters" className="flex flex-wrap items-end gap-x-3 gap-y-2">
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
      <label htmlFor={id} className="text-xs font-medium text-muted">
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
            className="group inline-flex h-6 items-center gap-1 rounded-md border border-border bg-surface pr-1 pl-2 text-sm text-primary transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong hover:bg-surface-muted"
          >
            {item.label}
            <X aria-hidden size={12} strokeWidth={2} className="text-muted group-hover:text-primary" />
          </button>
        </li>
      ))}
    </ul>
  );
}

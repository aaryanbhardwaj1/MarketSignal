"use client";

import { sourceClass, sourceType } from "@/lib/labels";
import { distinctValues, type LibraryFilters, type LibraryRow } from "@/lib/library-filters";
import { LIBRARY_STATUSES, libraryStatusLabel, type LibraryStatus } from "@/lib/status";
import { FilterBar, FilterSelect } from "../ui/filter-bar";
import { Checkbox } from "../ui/form-controls";

/** Type, category, status and version filters for the library table (all client-side). */
export function LibraryFilterBar({
  rows,
  filters,
  onChange,
  onReset,
}: {
  rows: readonly LibraryRow[];
  filters: LibraryFilters;
  onChange: (next: LibraryFilters) => void;
  onReset?: () => void;
}) {
  const types = distinctValues(rows, "sourceType");
  const classes = distinctValues(rows, "sourceClass");
  return (
    <FilterBar onReset={onReset}>
      <FilterSelect
        id="library-type"
        label="Type"
        value={filters.type}
        onChange={(type) => onChange({ ...filters, type })}
        options={[{ value: "", label: "All types" }, ...types.map((t) => ({ value: t, label: sourceType(t).label }))]}
      />
      <FilterSelect
        id="library-class"
        label="Category"
        value={filters.cls}
        onChange={(cls) => onChange({ ...filters, cls })}
        options={[{ value: "", label: "All categories" }, ...classes.map((c) => ({ value: c, label: sourceClass(c).label }))]}
      />
      <FilterSelect
        id="library-status"
        label="Status"
        value={filters.status}
        onChange={(status) => onChange({ ...filters, status: status as LibraryStatus | "" })}
        options={[{ value: "", label: "Any status" }, ...LIBRARY_STATUSES.map((s) => ({ value: s, label: libraryStatusLabel(s).label }))]}
      />
      <Checkbox
        id="library-superseded"
        label="Include superseded versions"
        className="mb-1.5"
        checked={filters.includeSuperseded}
        onChange={(e) => onChange({ ...filters, includeSuperseded: e.target.checked })}
      />
    </FilterBar>
  );
}

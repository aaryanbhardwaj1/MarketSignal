"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { SEARCH_MODES, SOURCE_CLASSES, type SearchMode, type SourceClass } from "@/lib/api/types";
import { SEARCH_MODE_LABELS, searchHref } from "@/lib/search";
import { Select, buttonClass } from "../ui/form-controls";

export function SearchForm({
  ws,
  q,
  mode,
  sourceClasses,
}: {
  ws: string;
  q: string;
  mode: SearchMode;
  sourceClasses: readonly SourceClass[];
}) {
  const router = useRouter();
  const [text, setText] = useState(q);
  const [selectedMode, setSelectedMode] = useState<SearchMode>(mode);
  const [classes, setClasses] = useState<readonly SourceClass[]>(sourceClasses);

  const toggleClass = (value: SourceClass, checked: boolean) =>
    setClasses((prev) => SOURCE_CLASSES.filter((c) => (c === value ? checked : prev.includes(c))));

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const query = text.trim();
    if (query) router.push(searchHref(ws, query, selectedMode, classes));
  };

  return (
    <form onSubmit={onSubmit} role="search" className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor="search-q" className="text-sm font-medium text-slate-700">
            Query
          </label>
          <input
            id="search-q"
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. gen z running"
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />
        </div>
        <div className="flex flex-col gap-1 sm:w-64">
          <label htmlFor="search-mode" className="text-sm font-medium text-slate-700">
            Mode
          </label>
          <Select
            id="search-mode"
            value={selectedMode}
            onChange={(e) => setSelectedMode(e.target.value as SearchMode)}
          >
            {SEARCH_MODES.map((m) => (
              <option key={m} value={m}>
                {SEARCH_MODE_LABELS[m]}
              </option>
            ))}
          </Select>
        </div>
        <button type="submit" className={buttonClass("primary")} disabled={!text.trim()}>
          Search
        </button>
      </div>
      <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <legend className="mb-1 text-sm font-medium text-slate-700">Source class (optional)</legend>
        {SOURCE_CLASSES.map((c) => (
          <label key={c} className="inline-flex items-center gap-1.5 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={classes.includes(c)}
              onChange={(e) => toggleClass(c, e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            {c}
          </label>
        ))}
      </fieldset>
    </form>
  );
}

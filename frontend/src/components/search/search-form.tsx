"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import type { SearchMode } from "@/lib/api/types";
import { buttonClass } from "../ui/form-controls";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "lexical", label: "Lexical" },
  { value: "dense", label: "Dense" },
];

export function searchHref(ws: string, q: string, mode: SearchMode): string {
  const params = new URLSearchParams({ q, mode });
  return `/w/${encodeURIComponent(ws)}/search?${params.toString()}`;
}

export function SearchForm({ ws, q, mode }: { ws: string; q: string; mode: SearchMode }) {
  const router = useRouter();
  const [text, setText] = useState(q);

  const submit = (nextMode: SearchMode) => {
    const query = text.trim();
    if (query) router.push(searchHref(ws, query, nextMode));
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(mode);
  };

  return (
    <form onSubmit={onSubmit} role="search" className="flex flex-col gap-3 sm:flex-row sm:items-end">
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
      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium text-slate-700">Lane</legend>
        <div className="inline-flex rounded-md shadow-sm" role="radiogroup">
          {MODES.map((m, i) => (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={mode === m.value}
              onClick={() => submit(m.value)}
              disabled={!text.trim()}
              className={`px-3 py-2 text-sm font-medium ring-1 ring-inset ring-slate-300 focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed ${
                i === 0 ? "rounded-l-md" : "-ml-px rounded-r-md"
              } ${mode === m.value ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-slate-700 hover:bg-slate-50"}`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </fieldset>
      <button type="submit" className={buttonClass("primary")} disabled={!text.trim()}>
        Search
      </button>
    </form>
  );
}

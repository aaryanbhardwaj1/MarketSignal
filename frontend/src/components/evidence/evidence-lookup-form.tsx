"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { evidenceViewerHref } from "@/lib/handles";
import { buttonClass } from "../ui/form-controls";

export function EvidenceLookupForm({ ws, initialHandle }: { ws: string; initialHandle: string }) {
  const router = useRouter();
  const [value, setValue] = useState(initialHandle);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const handle = value.trim();
    if (handle) router.push(evidenceViewerHref(ws, handle));
  };

  return (
    <form onSubmit={onSubmit} role="search" className="flex flex-col gap-2 sm:flex-row sm:items-end">
      <div className="flex flex-1 flex-col gap-1">
        <label htmlFor="evidence-handle" className="text-sm font-medium text-slate-700">
          Evidence handle
        </label>
        <input
          id="evidence-handle"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={`${ws}/SOURCE-CODE@v1:P1.B1`}
          spellCheck={false}
          autoComplete="off"
          className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
        />
      </div>
      <button type="submit" className={buttonClass("primary")} disabled={!value.trim()}>
        Resolve
      </button>
    </form>
  );
}

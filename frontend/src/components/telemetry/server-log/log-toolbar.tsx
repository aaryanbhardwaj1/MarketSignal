"use client";

import { useEffect, useState } from "react";
import { Pause, Play, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, Select } from "@/components/ui/form-controls";
import { PulseNode } from "@/components/motion/pulse-node";
import {
  DEFAULT_LOG_FILTERS,
  KIND_OPTIONS,
  LEVEL_OPTIONS,
  METHOD_OPTIONS,
  SEARCH_DEBOUNCE_MS,
  STATUS_OPTIONS,
  hasActiveFilters,
  type LogFilters,
} from "./log-model";

/** Search box that reports its trimmed value after a short pause in typing. */
function DebouncedSearch({ value, onChange }: { value: string; onChange: (q: string) => void }) {
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  // Adopt an outside change (a correlation-id click, "Clear filters") without an effect.
  if (value !== synced) {
    setSynced(value);
    setDraft(value);
  }
  useEffect(() => {
    if (draft === value) return;
    const id = window.setTimeout(() => onChange(draft), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [draft, value, onChange]);
  return (
    <span className="relative block min-w-80 flex-1">
      <label htmlFor="server-log-search" className="sr-only">
        Search events, routes, paths and ids
      </label>
      <Input
        id="server-log-search"
        type="search"
        value={draft}
        placeholder="Search events, routes, request or run ids"
        onChange={(e) => setDraft(e.target.value)}
        className="h-8 font-mono text-sm"
      />
    </span>
  );
}

export interface LogToolbarProps {
  filters: LogFilters;
  routes: readonly string[];
  live: boolean;
  onChange: (next: LogFilters) => void;
  onLiveChange: (live: boolean) => void;
  onRefresh: () => void;
}

export function LogToolbar({ filters, routes, live, onChange, onLiveChange, onRefresh }: LogToolbarProps) {
  const set = <K extends keyof LogFilters>(k: K, v: LogFilters[K]) => onChange({ ...filters, [k]: v });
  const routeOptions = [
    { value: "", label: "All routes" },
    ...[...new Set([...routes, ...(filters.route ? [filters.route] : [])])].map((r) => ({ value: r, label: r })),
  ];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <DebouncedSearch value={filters.q} onChange={(q) => set("q", q)} />
        <Select
          aria-label="Minimum level"
          controlSize="sm"
          value={filters.level}
          options={LEVEL_OPTIONS}
          onChange={(e) => set("level", e.target.value as LogFilters["level"])}
        />
        <Select
          aria-label="Kind"
          controlSize="sm"
          value={filters.kind}
          options={KIND_OPTIONS}
          onChange={(e) => set("kind", e.target.value as LogFilters["kind"])}
        />
        <Select aria-label="HTTP method" controlSize="sm" value={filters.method} options={METHOD_OPTIONS} onChange={(e) => set("method", e.target.value)} />
        <Select
          aria-label="Status class"
          controlSize="sm"
          value={filters.status_class}
          options={STATUS_OPTIONS}
          onChange={(e) => set("status_class", e.target.value as LogFilters["status_class"])}
        />
        <Select
          aria-label="Route"
          controlSize="sm"
          className="max-w-72"
          value={filters.route}
          options={routeOptions}
          onChange={(e) => set("route", e.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Checkbox
          id="server-log-noise"
          label={<span className="text-sm text-secondary">Show health checks</span>}
          checked={filters.include_noise}
          onChange={(e) => set("include_noise", e.target.checked)}
        />
        <div className="ml-auto flex items-center gap-2">
          {hasActiveFilters(filters) && (
            <Button variant="quiet" size="sm" onClick={() => onChange(DEFAULT_LOG_FILTERS)}>
              Clear filters
            </Button>
          )}
          <Button variant="ghost" size="sm" iconLeft={<RefreshCw aria-hidden />} onClick={onRefresh}>
            Refresh
          </Button>
          <Button
            variant="secondary"
            size="sm"
            aria-pressed={live}
            iconLeft={live ? <Pause aria-hidden /> : <Play aria-hidden />}
            onClick={() => onLiveChange(!live)}
          >
            <span className="inline-flex items-center gap-1.5">
              {live && <PulseNode tone="success" active size="sm" />}
              {live ? "Live" : "Paused"}
            </span>
          </Button>
        </div>
      </div>
    </div>
  );
}

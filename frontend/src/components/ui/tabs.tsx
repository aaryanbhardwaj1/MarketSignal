"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "@/lib/cx";

export interface TabItem {
  id: string;
  label: string;
  count?: number;
}

export const tabDomId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
export const panelDomId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

interface TabListProps {
  tabs: TabItem[];
  value: string;
  onChange?: (id: string) => void;
  /** Accessible name for the tab list. */
  label: string;
  /** Stable prefix linking tabs to `TabPanel`s; defaults to a generated id. */
  idPrefix?: string;
}

function TabList({ tabs, value, onChange, label, idPrefix }: TabListProps) {
  const generated = useId();
  const prefix = idPrefix ?? generated;
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = tabs.findIndex((t) => t.id === value);
    const last = tabs.length - 1;
    const next =
      event.key === "ArrowRight" ? (current >= last ? 0 : current + 1)
      : event.key === "ArrowLeft" ? (current <= 0 ? last : current - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    onChange?.(tabs[next].id);
    refs.current[next]?.focus();
  };

  return (
    <div role="tablist" aria-label={label} onKeyDown={move} className="flex gap-1 overflow-x-auto border-b border-border">
      {tabs.map((tab, index) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="tab"
            id={tabDomId(prefix, tab.id)}
            aria-selected={selected}
            aria-controls={panelDomId(prefix, tab.id)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange?.(tab.id)}
            className={cx(
              "-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-base font-medium transition-colors",
              selected ? "border-accent text-primary" : "border-transparent text-muted hover:text-primary",
            )}
          >
            {tab.label}
            {tab.count != null && (
              <span className="rounded-sm bg-surface-muted px-1.5 text-xs tabular-nums text-secondary">{tab.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function UrlTabList(props: TabListProps & { param: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromUrl = params.get(props.param);
  const value = props.tabs.some((t) => t.id === fromUrl) ? (fromUrl as string) : props.value;
  const change = (id: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(props.param, id);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    props.onChange?.(id);
  };
  return <TabList {...props} value={value} onChange={change} />;
}

/**
 * ARIA tablist. Arrow keys, Home and End move between tabs (roving tabindex).
 * With `param`, the selected tab is read from and written to that URL search parameter;
 * pages using `param` must render Tabs inside a Suspense boundary.
 */
export function Tabs(props: TabListProps & { param?: string }) {
  const { param, ...rest } = props;
  return param ? <UrlTabList {...rest} param={param} /> : <TabList {...rest} />;
}

export function TabPanel({
  idPrefix,
  id,
  hidden = false,
  children,
}: {
  idPrefix: string;
  id: string;
  hidden?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={panelDomId(idPrefix, id)}
      aria-labelledby={tabDomId(idPrefix, id)}
      hidden={hidden}
      tabIndex={0}
      className="pt-4 focus-visible:outline-offset-4"
    >
      {children}
    </div>
  );
}

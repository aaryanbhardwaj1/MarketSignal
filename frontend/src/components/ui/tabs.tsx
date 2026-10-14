"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useLayoutEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
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

/**
 * Positions one underline under the selected tab so it can slide between tabs. Writes straight to
 * the DOM (no state): until it has measured (server render, jsdom) the selected tab draws its own
 * line, and the list gets `data-indicator="on"` once the sliding line takes over.
 */
function useIndicator(
  listRef: { current: HTMLDivElement | null },
  barRef: { current: HTMLSpanElement | null },
  refs: { current: Array<HTMLButtonElement | null> },
  index: number,
  labels: string,
) {
  useLayoutEffect(() => {
    const list = listRef.current;
    const bar = barRef.current;
    const tab = refs.current[index];
    if (!list || !bar || !tab) return;
    const place = () => {
      if (tab.offsetWidth === 0) return;
      bar.style.width = `${tab.offsetWidth}px`;
      bar.style.transform = `translateX(${tab.offsetLeft}px)`;
      if (list.dataset.indicator !== "on") {
        list.dataset.indicator = "on";
        // Enable the slide only after the first placement, so it does not sweep in from the left.
        requestAnimationFrame(() => {
          bar.dataset.ready = "true";
        });
      }
    };
    place();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(place);
    observer.observe(tab);
    return () => observer.disconnect();
  }, [listRef, barRef, refs, index, labels]);
}

function TabList({ tabs, value, onChange, label, idPrefix }: TabListProps) {
  const generated = useId();
  const prefix = idPrefix ?? generated;
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const listRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLSpanElement>(null);
  useIndicator(
    listRef,
    barRef,
    refs,
    tabs.findIndex((t) => t.id === value),
    tabs.map((t) => `${t.label}${t.count ?? ""}`).join("|"),
  );

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
    <div
      ref={listRef}
      role="tablist"
      aria-label={label}
      onKeyDown={move}
      className="group/tabs relative flex gap-1 overflow-x-auto border-b border-border"
    >
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
            // Only the selected panel is rendered, so only it can be referenced.
            aria-controls={selected ? panelDomId(prefix, tab.id) : undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange?.(tab.id)}
            className={cx(
              // Inset focus ring: the scrolling tab list would clip an outset one.
              "-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-base font-medium",
              "transition-colors duration-(--duration-fast) ease-standard focus-visible:outline-offset-[-2px]",
              // Until the sliding indicator is measured (server render), the selected tab draws its own line.
              selected ? "border-accent group-data-[indicator=on]/tabs:border-transparent" : "border-transparent",
              selected ? "text-primary" : "text-muted hover:text-primary",
            )}
          >
            {tab.label}
            {tab.count != null && (
              <span
                className={cx(
                  "rounded-md px-1.5 text-xs tabular-nums",
                  selected ? "bg-accent-subtle text-accent-text" : "bg-surface-muted text-secondary",
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
      <span
        ref={barRef}
        aria-hidden
        className={cx(
          "pointer-events-none absolute bottom-0 left-0 h-0.5 w-0 bg-accent opacity-0 group-data-[indicator=on]/tabs:opacity-100",
          "data-[ready=true]:transition-[transform,width] data-[ready=true]:duration-(--duration-base) data-[ready=true]:ease-standard motion-reduce:transition-none",
        )}
      />
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

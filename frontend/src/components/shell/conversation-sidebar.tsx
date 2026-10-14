"use client";

import { ListFilter, PanelLeftClose, PanelLeftOpen, Search, SquarePen } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type RefObject } from "react";
import { cx } from "@/lib/cx";
import { askHref } from "@/lib/routes";
import { IconButton, iconButtonClass } from "../ui/icon-button";
import { Kbd, useModShortcut } from "../ui/kbd";
import { Popover } from "../ui/popover";
import { Tooltip } from "../ui/tooltip";
import { ConversationList } from "./conversation-list";
import { useEmitNewChat } from "./new-chat-signal";

export const CONVERSATION_SEARCH_ID = "conversation-search";
const SEARCH_DEBOUNCE_MS = 250;

/** "New chat": always a real link to the empty Chat page; also signals Chat to clear its draft. */
function NewChatLink({ ws, compact, onNavigate }: { ws: string; compact: boolean; onNavigate?: () => void }) {
  const emit = useEmitNewChat();
  const onClick = () => {
    emit();
    onNavigate?.();
  };
  if (compact) {
    return (
      <Tooltip content="New chat" side="right" decorative>
        <Link href={askHref(ws)} aria-label="New chat" onClick={onClick} className={iconButtonClass("md")}>
          <SquarePen aria-hidden />
        </Link>
      </Tooltip>
    );
  }
  return (
    <Link
      href={askHref(ws)}
      onClick={onClick}
      className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded-md px-2.5 text-sm font-medium text-primary transition-colors duration-(--duration-fast) hover:bg-surface-muted"
    >
      <SquarePen aria-hidden className="size-4 text-secondary" />
      New chat
    </Link>
  );
}

function CollapseToggle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const shortcut = useModShortcut("\\");
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  return (
    <IconButton
      label={label}
      icon={collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
      aria-keyshortcuts="Meta+Backslash Control+Backslash"
      onClick={onToggle}
      tooltipSide={collapsed ? "right" : "bottom"}
      tooltip={
        <>
          {label}
          <Kbd>{shortcut}</Kbd>
        </>
      }
    />
  );
}

/** Debounced search box (live results; Escape clears). */
function ConversationSearch({ onChange, inputRef }: { onChange: (q: string) => void; inputRef: RefObject<HTMLInputElement | null> }) {
  const [value, setValue] = useState("");
  const latest = useRef(onChange);
  useEffect(() => {
    latest.current = onChange;
  });
  useEffect(() => {
    const t = setTimeout(() => latest.current(value.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [value]);
  return (
    <div role="search" className="relative min-w-0 flex-1">
      <label htmlFor={CONVERSATION_SEARCH_ID} className="sr-only">
        Search conversations
      </label>
      <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted" />
      <input
        ref={inputRef}
        id={CONVERSATION_SEARCH_ID}
        type="search"
        value={value}
        placeholder="Search conversations"
        autoComplete="off"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && value) {
            e.stopPropagation();
            setValue("");
          }
        }}
        className="h-8 w-full rounded-md border border-border bg-canvas pr-2 pl-8 text-sm text-primary placeholder:text-muted focus:border-border-strong focus:bg-surface"
      />
    </div>
  );
}

function FilterMenu({ answeredOnly, onChange }: { answeredOnly: boolean; onChange: (v: boolean) => void }) {
  return (
    <Popover
      align="end"
      label="Conversation filters"
      trigger={
        <button type="button" aria-label="Filter conversations" className={iconButtonClass("md", answeredOnly)}>
          <ListFilter aria-hidden />
        </button>
      }
      panelClassName="min-w-48"
    >
      <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-primary hover:bg-surface-muted">
        <input
          type="checkbox"
          checked={answeredOnly}
          onChange={(e) => onChange(e.target.checked)}
          className="size-3.5 accent-(--color-accent)"
        />
        Answered only
      </label>
    </Popover>
  );
}

/**
 * Left sidebar: conversations only. Docked, it collapses to a rail (New chat, Search, expand)
 * with a width transition; the expanded and rail layers keep fixed widths and cross-fade, so
 * nothing reflows mid-animation. `variant="sheet"` is the small-screen overlay body (never collapsed).
 */
export function ConversationSidebar({
  ws,
  collapsed = false,
  onToggle,
  onNavigate,
  variant = "docked",
  now,
}: {
  ws: string;
  collapsed?: boolean;
  onToggle?: () => void;
  onNavigate?: () => void;
  variant?: "docked" | "sheet";
  now: Date;
}) {
  const [q, setQ] = useState("");
  const [answeredOnly, setAnsweredOnly] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const [focusSearch, setFocusSearch] = useState(false);
  const docked = variant === "docked";

  useEffect(() => {
    if (!focusSearch || collapsed) return;
    searchRef.current?.focus();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFocusSearch(false);
  }, [focusSearch, collapsed]);

  const expanded = (
    <div className={cx("flex h-full flex-col", docked && "w-(--width-sidebar)")}>
      <div className="flex flex-col gap-2 px-2 pt-2.5 pb-2">
        <div className="flex items-center gap-1">
          <NewChatLink ws={ws} compact={false} onNavigate={onNavigate} />
          {docked && onToggle && <CollapseToggle collapsed={false} onToggle={onToggle} />}
        </div>
        <div className="flex items-center gap-1">
          <ConversationSearch onChange={setQ} inputRef={searchRef} />
          <FilterMenu answeredOnly={answeredOnly} onChange={setAnsweredOnly} />
        </div>
      </div>
      <nav aria-label="Conversations" className="min-h-0 flex-1 overflow-y-auto px-2">
        <ConversationList ws={ws} q={q} answeredOnly={answeredOnly} now={now} onNavigate={onNavigate} />
      </nav>
    </div>
  );

  if (!docked) return expanded;

  return (
    <div className="relative h-full">
      <div
        inert={collapsed}
        aria-hidden={collapsed || undefined}
        className={cx(
          "absolute inset-y-0 left-0 transition-opacity duration-(--duration-base) ease-standard",
          collapsed ? "opacity-0" : "opacity-100",
        )}
      >
        {expanded}
      </div>
      <div
        inert={!collapsed}
        aria-hidden={!collapsed || undefined}
        className={cx(
          "absolute inset-y-0 left-0 flex w-(--width-rail) flex-col items-center gap-1 pt-2.5 transition-opacity duration-(--duration-base) ease-standard",
          collapsed ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      >
        {onToggle && <CollapseToggle collapsed onToggle={onToggle} />}
        <NewChatLink ws={ws} compact onNavigate={onNavigate} />
        <IconButton
          label="Search conversations"
          icon={<Search />}
          tooltipSide="right"
          onClick={() => {
            onToggle?.();
            setFocusSearch(true);
          }}
        />
      </div>
    </div>
  );
}

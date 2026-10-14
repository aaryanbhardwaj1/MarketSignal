"use client";

import { Activity, ChartColumnBig, Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Ref } from "react";
import { BrandLockup } from "../brand/brand-mark";
import { IconButton, IconLink } from "../ui/icon-button";
import { ModelStatusDot } from "./model-status";
import { DEV_TOOLS, activeNavId, type NavId } from "./nav";
import { PrimaryNav } from "./primary-nav";
import { WorkspaceControl } from "./workspace-control";
import { askHref } from "@/lib/routes";

const DEV_ICONS: Partial<Record<NavId, typeof Activity>> = {
  telemetry: Activity,
  evaluation: ChartColumnBig,
};

/** Telemetry and RAG Evaluation as icon links, grouped and labelled as developer tooling. */
export function DevTools({ ws }: { ws: string }) {
  const pathname = usePathname() ?? "";
  const active = activeNavId(pathname, ws);
  return (
    <div role="group" aria-label="Developer tools" className="flex items-center gap-0.5">
      {DEV_TOOLS.map((tool) => {
        const Icon = DEV_ICONS[tool.id] ?? Activity;
        return (
          <IconLink
            key={tool.id}
            href={tool.href(ws)}
            label={tool.label}
            icon={<Icon aria-hidden />}
            active={active === tool.id}
            tooltip={
              <>
                <span className="font-normal text-white/60">Developer tools ·</span> {tool.label}
              </>
            }
          />
        );
      })}
    </div>
  );
}

/**
 * Persistent top bar: brand (to Chat) and workspace on the left, the four business sections in
 * the centre, live-model status and the developer tools on the right. Below `lg` a menu button
 * opens the conversation sheet; below `md` the section links move into that sheet as well.
 */
export function TopBar({
  ws,
  menuOpen,
  onMenu,
  menuButtonRef,
  menuId,
}: {
  ws: string;
  menuOpen: boolean;
  onMenu: () => void;
  menuButtonRef: Ref<HTMLButtonElement>;
  menuId: string;
}) {
  return (
    <header className="sticky top-0 z-40 h-(--height-topbar) border-b border-border bg-surface">
      <div className="grid h-full grid-cols-[1fr_auto_1fr] items-center gap-3 px-2 md:px-3">
        <div className="flex min-w-0 items-center gap-1">
          <IconButton
            ref={menuButtonRef}
            label="Conversations and navigation"
            icon={<Menu />}
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={onMenu}
            className="lg:hidden"
            tooltip={false}
          />
          <Link href={askHref(ws)} aria-label="MarketSignal, go to Chat" className="flex h-8 shrink-0 items-center rounded-md px-1.5">
            <BrandLockup size={20} />
          </Link>
          <span aria-hidden className="mx-1 hidden h-4 w-px bg-border sm:block" />
          <div className="hidden min-w-0 sm:flex">
            <WorkspaceControl ws={ws} />
          </div>
        </div>

        <PrimaryNav ws={ws} className="hidden md:block" />

        <div className="col-start-3 flex items-center justify-end gap-1">
          <ModelStatusDot />
          <span aria-hidden className="mx-1 h-4 w-px bg-border" />
          <DevTools ws={ws} />
        </div>
      </div>
    </header>
  );
}

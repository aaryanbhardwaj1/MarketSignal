"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SECTIONS = [
  { slug: "", label: "Dashboard" },
  { slug: "sources", label: "Sources" },
  { slug: "evidence", label: "Evidence" },
  { slug: "search", label: "Search" },
] as const;

export function WorkspaceSubnav({ ws }: { ws: string }) {
  const pathname = usePathname() ?? "";
  const base = `/w/${encodeURIComponent(ws)}`;

  return (
    <div className="border-b border-slate-200 bg-white">
      <nav
        aria-label="Workspace sections"
        className="mx-auto flex w-full max-w-7xl items-center gap-1 overflow-x-auto px-4 sm:px-6"
      >
        <span className="mr-3 py-3 font-mono text-xs font-semibold text-slate-500">{ws}</span>
        {SECTIONS.map(({ slug, label }) => {
          const href = slug ? `${base}/${slug}` : base;
          const active = slug ? pathname.startsWith(href) : pathname === href;
          return (
            <Link
              key={label}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`whitespace-nowrap border-b-2 px-3 py-3 text-sm font-medium ${
                active
                  ? "border-indigo-600 text-indigo-700"
                  : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

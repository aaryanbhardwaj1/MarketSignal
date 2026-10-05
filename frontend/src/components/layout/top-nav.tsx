import Link from "next/link";
import { ApiStatus } from "./api-status";
import { WorkspaceSwitcher } from "./workspace-switcher";

export function TopNav() {
  return (
    <header className="bg-slate-900 text-white">
      <nav
        aria-label="Primary"
        className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6"
      >
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span aria-hidden className="grid h-7 w-7 place-items-center rounded-md bg-indigo-500 text-sm">
            M
          </span>
          <span>MarketSignal</span>
        </Link>
        <div className="flex items-center gap-3">
          <WorkspaceSwitcher />
          <ApiStatus />
        </div>
      </nav>
    </header>
  );
}

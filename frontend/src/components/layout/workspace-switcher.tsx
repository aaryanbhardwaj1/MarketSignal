"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { listWorkspaces } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";

/** Extracts the workspace code from `/w/<ws>/...` paths. */
export function workspaceFromPath(pathname: string | null): string | null {
  const match = /^\/w\/([^/]+)/.exec(pathname ?? "");
  return match ? decodeURIComponent(match[1]) : null;
}

export function WorkspaceSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const current = workspaceFromPath(pathname);
  const { data, isError } = useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => listWorkspaces(signal),
  });

  if (isError) return null;

  const onChange = (code: string) => {
    if (!code) {
      router.push("/");
      return;
    }
    // Keep the user on the same sub-page (sources/search/evidence) when switching.
    const section = /^\/w\/[^/]+\/(sources|search|evidence)/.exec(pathname ?? "")?.[1];
    router.push(`/w/${encodeURIComponent(code)}${section ? `/${section}` : ""}`);
  };

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="workspace-switcher" className="sr-only">
        Workspace
      </label>
      <select
        id="workspace-switcher"
        value={current ?? ""}
        onChange={(event) => onChange(event.target.value)}
        className="max-w-[11rem] rounded-md border border-slate-600 bg-slate-800 px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-400 sm:max-w-xs"
      >
        <option value="">All workspaces</option>
        {current && !data?.some((w) => w.code === current) && <option value={current}>{current}</option>}
        {data?.map((w) => (
          <option key={w.id} value={w.code}>
            {w.code}
          </option>
        ))}
      </select>
    </div>
  );
}

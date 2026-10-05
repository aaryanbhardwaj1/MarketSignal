import { SearchView } from "@/components/search/search-view";
import type { SearchMode } from "@/lib/api/types";
import { firstParam } from "@/lib/search-params";

export default async function SearchPage({ params, searchParams }: PageProps<"/w/[ws]/search">) {
  const { ws } = await params;
  const query = await searchParams;
  const mode: SearchMode = firstParam(query.mode) === "dense" ? "dense" : "lexical";
  return <SearchView ws={ws} q={(firstParam(query.q) ?? "").trim()} mode={mode} />;
}

import { SearchView } from "@/components/search/search-view";
import { parseSearchMode, parseSourceClasses } from "@/lib/search";
import { firstParam } from "@/lib/search-params";

export default async function SearchPage({ params, searchParams }: PageProps<"/w/[ws]/search">) {
  const { ws } = await params;
  const query = await searchParams;
  return (
    <SearchView
      ws={ws}
      q={(firstParam(query.q) ?? "").trim()}
      mode={parseSearchMode(firstParam(query.mode))}
      sourceClasses={parseSourceClasses(query.source_class)}
    />
  );
}

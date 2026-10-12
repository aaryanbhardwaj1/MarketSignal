"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { searchWorkspace } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import { SOURCE_CLASSES, type SearchItem, type SourceClass } from "@/lib/api/types";
import { segmentHighlight } from "@/lib/highlight";
import { sourceClass, sourceType } from "@/lib/labels";
import { filterSearchGroups, type LibraryFilters } from "@/lib/library-filters";
import { DEFAULT_SEARCH_MODE, groupSearchResults, type SearchGroup } from "@/lib/search";
import { businessLocator, formatNumber } from "@/lib/format";
import { useEvidenceDrawer } from "../evidence/drawer-context";
import { Button } from "../ui/button";
import { Callout } from "../ui/callout";
import { DevDetails } from "../ui/disclosure";
import { Section } from "../ui/section";
import { Card } from "../ui/card";
import { CardGridSkeleton, EmptyState, ErrorState } from "../ui/states";

const RESULT_LIMIT = 20;

function asSourceClasses(cls: string): SourceClass[] {
  return (SOURCE_CLASSES as readonly string[]).includes(cls) ? [cls as SourceClass] : [];
}

function Snippet({ item }: { item: SearchItem }) {
  const { before, mark, after, valid } = segmentHighlight(item.snippet.text, item.snippet.mark_start, item.snippet.mark_end);
  return (
    <p className="line-clamp-3 text-base text-secondary">
      {item.snippet.truncated_left && "… "}
      {valid ? (
        <>
          {before}
          <mark className="rounded-sm bg-accent-subtle px-0.5 text-primary">{mark}</mark>
          {after}
        </>
      ) : (
        item.snippet.text
      )}
      {item.snippet.truncated_right && " …"}
    </p>
  );
}

const PASSAGES_PER_SOURCE = 3;

function SourceGroup({ group, onOpen }: { group: SearchGroup; onOpen: (item: SearchItem) => void }) {
  const [expanded, setExpanded] = useState(false);
  const hidden = group.items.length - PASSAGES_PER_SOURCE;
  const items = expanded ? group.items : group.items.slice(0, PASSAGES_PER_SOURCE);
  return (
    <Card as="li" padding="none">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-2.5">
        <h3 className="min-w-0 truncate text-base font-semibold text-primary">{group.title}</h3>
        <p className="text-sm text-muted">
          {sourceClass(group.sourceClass).label} · {sourceType(group.sourceType).label} ·{" "}
          {group.items.length === 1 ? "1 passage" : `${formatNumber(group.items.length)} passages`}
        </p>
      </div>
      <ul className="divide-y divide-border">
        {items.map((item) => (
          <li key={`${item.handle}-${item.anchor.child_id}`}>
            <button
              type="button"
              onClick={() => onOpen(item)}
              aria-label={`Open passage: ${[group.title, businessLocator(item.locator_label)].filter(Boolean).join(", ")}`}
              className="flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-surface-muted/60"
            >
              <span className="text-sm font-medium text-secondary">{businessLocator(item.locator_label)}</span>
              <Snippet item={item} />
            </button>
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <div className="border-t border-border px-4 py-2">
          <Button variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Show fewer passages" : `Show ${formatNumber(hidden)} more from this source`}
          </Button>
        </div>
      )}
    </Card>
  );
}

/** One plain sentence describing the search state, for the page's screen-reader status region. */
export function searchSummary(state: "pending" | "error" | "done", passages: number, sources: number): string {
  if (state === "pending") return "Searching the library";
  if (state === "error") return "Search could not be completed";
  if (passages === 0) return "No passages match this search";
  return `${formatNumber(passages)} ${passages === 1 ? "passage" : "passages"} from ${formatNumber(sources)} ${sources === 1 ? "source" : "sources"}`;
}

/** Library search: passages grouped by source, with snippet and location; no ranking scores. */
export function LibrarySearchResults({
  ws,
  q,
  filters,
  onClearSearch,
  onClearFilters,
  onSummary,
}: {
  ws: string;
  q: string;
  filters: LibraryFilters;
  onClearSearch: () => void;
  onClearFilters?: () => void;
  /** Receives a plain sentence ("12 passages from 4 sources") whenever the result changes. */
  onSummary?: (text: string) => void;
}) {
  const drawer = useEvidenceDrawer();
  const classes = asSourceClasses(filters.cls);
  const query = useQuery({
    queryKey: queryKeys.search(ws, q, DEFAULT_SEARCH_MODE, RESULT_LIMIT, classes),
    queryFn: ({ signal }) => searchWorkspace(ws, { q, mode: DEFAULT_SEARCH_MODE, k: RESULT_LIMIT, sourceClasses: classes }, signal),
  });

  const openItem = (item: SearchItem) =>
    drawer.openEvidence({
      handle: item.handle,
      childId: item.anchor.child_id,
      charStart: item.anchor.char_start,
      charEnd: item.anchor.char_end,
    });
  const groups = query.data ? filterSearchGroups(groupSearchResults(query.data.items), filters) : [];
  const passageCount = groups.reduce((n, g) => n + g.items.length, 0);
  const summary = searchSummary(query.isPending ? "pending" : query.isError ? "error" : "done", passageCount, groups.length);
  useEffect(() => {
    onSummary?.(summary);
  }, [summary, onSummary]);
  const clearSearch = (
    <Button variant="ghost" size="sm" onClick={onClearSearch}>
      Clear search
    </Button>
  );

  return (
    <Section
      title={`Passages matching “${q}”`}
      description={
        query.data && passageCount > 0
          ? `${formatNumber(passageCount)} passages from ${formatNumber(groups.length)} sources, most relevant first. Select a passage to read it in context.`
          : undefined
      }
      actions={clearSearch}
    >
      {query.isPending ? (
        <CardGridSkeleton label="Searching the library" count={3} lines={3} gap="sm" />
      ) : query.isError ? (
        <ErrorState
          title="Search could not be completed"
          error={query.error}
          retry={() => void query.refetch()}
        />
      ) : groups.length === 0 ? (
        <EmptyState
          title="No passages match this search"
          description={onClearFilters ? "Try clearing the filters or using different words." : "Try different or fewer words."}
          action={
            onClearFilters ? (
              <Button variant="secondary" onClick={onClearFilters}>
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {query.data.flags.length > 0 && (
            <Callout tone="info" title="Search ran in a reduced mode">
              Results are still drawn from the library, but their order may be less precise than usual.
            </Callout>
          )}
          <ul aria-label="Search results by source" className="flex flex-col gap-3">
            {groups.map((group) => (
              <SourceGroup key={group.sourceCode} group={group} onOpen={openItem} />
            ))}
          </ul>
          <DevDetails data={{ mode: query.data.mode, flags: query.data.flags, trace_id: query.data.trace_id, timings_ms: query.data.timings_ms }} />
        </div>
      )}
    </Section>
  );
}

"use client";

import type { Evidence } from "@/lib/api/types";
import type { ActiveSpan } from "@/lib/highlight";
import { Card } from "../ui/card";
import { CopyButton } from "../ui/copy-button";
import { ChildSpanList } from "./child-span-list";
import { ContextExcerpts } from "./context-excerpts";
import { HighlightedText } from "./highlighted-text";
import { ProvenancePanel } from "./provenance-panel";
import { SourceMetaPanel } from "./source-meta-panel";
import { VersionNotice } from "./version-notice";

function HeadingPath({ path }: { path: string[] }) {
  if (path.length === 0) return null;
  return (
    <nav aria-label="Heading path">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-slate-600">
        {path.map((heading, i) => (
          <li key={`${i}-${heading}`} className="flex items-center gap-1">
            {i > 0 && (
              <span aria-hidden className="text-slate-400">
                /
              </span>
            )}
            <span className={i === path.length - 1 ? "font-medium text-slate-900" : undefined}>
              {heading}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function EvidenceDetail({
  ws,
  evidence,
  span,
  onSelectChild,
}: {
  ws: string;
  evidence: Evidence;
  span: ActiveSpan | null;
  onSelectChild: (childId: string | null) => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <code className="break-all font-mono text-sm font-semibold text-slate-900">
            {evidence.handle}
          </code>
          <CopyButton value={evidence.handle} label="Copy handle" />
        </div>
        <p className="text-sm text-slate-700">
          <span className="font-medium">{evidence.locator_label}</span>
        </p>
        <HeadingPath path={evidence.heading_path} />
      </div>

      <VersionNotice ws={ws} handle={evidence.handle} source={evidence.source} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex flex-col gap-6">
          <Card
            title="Parent text"
            actions={
              <span className="text-xs text-slate-500">
                {span
                  ? `Highlighting child span [${span.charStart}, ${span.charEnd})`
                  : "No span selected"}
              </span>
            }
          >
            <HighlightedText text={evidence.text} span={span} />
          </Card>
          <Card title="Surrounding context">
            <ContextExcerpts
              previous={evidence.context.previous_excerpt}
              next={evidence.context.next_excerpt}
            />
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          <Card title={`Child spans (${evidence.children.length})`}>
            <ChildSpanList
              text={evidence.text}
              spans={evidence.children}
              activeId={span?.childId ?? null}
              onSelect={onSelectChild}
            />
          </Card>
          <Card title="Source">
            <SourceMetaPanel ws={ws} evidence={evidence} />
          </Card>
          <Card title="Provenance">
            <ProvenancePanel evidence={evidence} />
          </Card>
        </div>
      </div>
    </div>
  );
}

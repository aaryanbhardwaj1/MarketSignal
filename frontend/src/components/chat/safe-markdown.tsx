import { useMemo } from "react";
import Markdown, { type Components } from "react-markdown";
import {
  prepareMarkdown,
  splitPlaceholders,
  type ChipToken,
  type CitationContext,
} from "@/lib/citations";
import { CitationChip } from "./citation-chip";

/**
 * The only elements answer Markdown may produce. No `a` (links render as their text) and no
 * `img`; anything else is unwrapped to its text, raw HTML is skipped entirely. `span` is never
 * produced by Markdown itself (HTML is skipped): it only carries the chip placeholders below.
 */
export const BLOCK_ELEMENTS = [
  "p",
  "strong",
  "em",
  "ul",
  "ol",
  "li",
  "h3",
  "h4",
  "code",
  "blockquote",
] as const;
const INLINE_ELEMENTS = ["strong", "em", "code"] as const;
const CHIP_TAG = "span";

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

const HEADING_MAP: Readonly<Record<string, string>> = { h1: "h3", h2: "h3", h5: "h4", h6: "h4" };

function expandText(node: HastNode): HastNode[] {
  if (node.type !== "text" || !node.value) return [node];
  const parts = splitPlaceholders(node.value);
  if (parts.length === 1 && parts[0].kind === "text") return [node];
  return parts.map((part) =>
    part.kind === "text"
      ? { type: "text", value: part.text }
      : { type: "element", tagName: CHIP_TAG, properties: { dataChip: String(part.index) }, children: [] },
  );
}

function transform(node: HastNode): void {
  if (node.type === "element" && node.tagName && HEADING_MAP[node.tagName]) {
    node.tagName = HEADING_MAP[node.tagName];
  }
  if (!node.children) return;
  node.children = node.children.flatMap(expandText);
  node.children.forEach(transform);
}

/** Rehype plugin: placeholder characters in text nodes become `<span data-chip=N>` nodes. */
function rehypeCitationChips() {
  return (tree: HastNode) => transform(tree);
}

const REHYPE_PLUGINS = [rehypeCitationChips];
const noUrls = () => "";

function chipIndex(node: HastNode | undefined): number | null {
  const raw = node?.properties?.dataChip;
  const index = typeof raw === "string" || typeof raw === "number" ? Number(raw) : NaN;
  return Number.isInteger(index) ? index : null;
}

function buildComponents(tokens: readonly ChipToken[], ws: string, inline: boolean): Components {
  const chip: Components["span"] = ({ node }) => {
    const index = chipIndex(node as HastNode | undefined);
    const token = index === null ? undefined : tokens[index];
    return token ? <CitationChip token={token} ws={ws} /> : null;
  };
  if (inline) return { span: chip };
  return {
    span: chip,
    p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
    ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
    ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    h3: ({ children }) => <h3 className="mt-4 mb-1 text-sm font-semibold text-slate-900">{children}</h3>,
    h4: ({ children }) => <h4 className="mt-3 mb-1 text-sm font-medium text-slate-800">{children}</h4>,
    code: ({ children }) => (
      <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-2 border-slate-300 pl-3 text-slate-600">{children}</blockquote>
    ),
  };
}

export interface SafeMarkdownProps {
  /** Untrusted Markdown (model draft or canonical final content). */
  text: string;
  ws: string;
  citations?: CitationContext;
  /** Render a single unit inline (no block elements), e.g. one answer sentence. */
  inline?: boolean;
  className?: string;
}

/**
 * Plain-text-safe Markdown renderer shared by the streaming draft and the verified final answer.
 * Never uses dangerouslySetInnerHTML; citation markers become chip components.
 */
export function SafeMarkdown({ text, ws, citations, inline = false, className }: SafeMarkdownProps) {
  const prepared = useMemo(() => prepareMarkdown(text, citations), [text, citations]);
  const components = useMemo(
    () => buildComponents(prepared.tokens, ws, inline),
    [prepared.tokens, ws, inline],
  );
  const allowed = inline ? [...INLINE_ELEMENTS, CHIP_TAG] : [...BLOCK_ELEMENTS, CHIP_TAG];
  const markdown = (
    <Markdown
      allowedElements={allowed}
      unwrapDisallowed
      skipHtml
      urlTransform={noUrls}
      rehypePlugins={REHYPE_PLUGINS}
      components={components}
    >
      {prepared.source}
    </Markdown>
  );
  return inline ? (
    <span className={className}>{markdown}</span>
  ) : (
    <div className={`text-sm text-slate-800 ${className ?? ""}`}>{markdown}</div>
  );
}

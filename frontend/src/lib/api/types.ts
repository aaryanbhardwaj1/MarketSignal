/** Wire types for the MarketSignal Phase 1 API. Field names mirror the JSON exactly. */

export const SOURCE_CLASSES = ["internal", "customer", "competitor", "market", "financial"] as const;
export type SourceClass = (typeof SOURCE_CLASSES)[number];

export const CONFIDENTIALITY_LEVELS = ["public", "internal", "confidential", "restricted"] as const;
export type Confidentiality = (typeof CONFIDENTIALITY_LEVELS)[number];

export const NON_TERMINAL_STATUSES = ["queued", "parsing", "chunking", "embedding", "indexing"] as const;
export const TERMINAL_STATUSES = ["ready", "ready_degraded", "failed", "superseded", "purged"] as const;
export type VersionStatus =
  | (typeof NON_TERMINAL_STATUSES)[number]
  | (typeof TERMINAL_STATUSES)[number];

export const SEARCH_MODES = ["full", "hybrid", "dense", "lexical", "rerank"] as const;
export type SearchMode = (typeof SEARCH_MODES)[number];

export interface Workspace {
  id: string;
  code: string;
  name: string;
  description: string | null;
  default_persona: string;
  created_at: string;
}

export interface WorkspaceDetail extends Omit<Workspace, "created_at"> {
  corpus_version: number;
  sources_by_class: Record<string, number>;
  sources_by_status: Record<string, number>;
  parent_count: number;
  child_count: number;
}

export interface CreateWorkspaceInput {
  code: string;
  name: string;
  description?: string;
}

export interface VersionTimings {
  parse_ms?: number;
  chunk_ms?: number;
  embed_ms?: number;
  index_ms?: number;
  health_ms?: number;
  total_ms?: number;
  parents?: number;
  children?: number;
  bytes?: number;
  [key: string]: number | undefined;
}

export interface VersionHealth {
  ok: boolean;
  checked?: number;
  reason?: string;
  [key: string]: unknown;
}

export interface SourceVersion {
  version_id: string;
  version: number;
  status: VersionStatus;
  source_class: SourceClass;
  confidentiality: Confidentiality;
  original_filename: string | null;
  byte_size: number | null;
  error_code: string | null;
  error_detail: string | null;
  warnings: string[];
  parent_count: number | null;
  child_count: number | null;
  embedding_model: string | null;
  timings: VersionTimings | null;
  health: VersionHealth | null;
  attempts: number;
  created_at: string;
  ready_at: string | null;
}

export interface SourceSummary {
  source_id: string;
  source_code: string;
  title: string;
  source_type: string;
  deleted: boolean;
  current_version_id: string | null;
  latest: SourceVersion | null;
}

export interface SourceDetail extends Omit<SourceSummary, "latest"> {
  versions: SourceVersion[];
}

export interface UploadSourceInput {
  file: File;
  source_class: SourceClass;
  confidentiality: Confidentiality;
  title?: string;
  source_code?: string;
}

export interface UploadSourceResult {
  source_id: string;
  source_code: string;
  version_id: string;
  version: number;
  status: VersionStatus;
  created: boolean;
  duplicate_of: string | null;
  status_url: string;
}

export interface DeleteSourceResult {
  source_code: string;
  versions_purged: number;
  corpus_version: number;
  status: "purged";
}

export interface EvidenceChild {
  child_id: string;
  ordinal: number;
  kind: string;
  char_start: number;
  char_end: number;
}

export interface EvidenceHighlight {
  child_id: string;
  char_start: number;
  char_end: number;
  text: string;
}

export interface EvidenceSource {
  source_id: string;
  source_code: string;
  title: string;
  source_type: string;
  source_class: SourceClass;
  confidentiality: Confidentiality;
  version: number;
  version_status: VersionStatus;
  latest_version: number | null;
  is_latest: boolean;
  original_filename: string | null;
  mime_type: string | null;
  ingested_at: string | null;
}

export interface EvidenceProvenance {
  source_content_sha256: string | null;
  parent_content_sha256: string | null;
  parser_version: string | null;
  structure_version: string | null;
  chunking_policy_version: string | null;
  embedding_model: string | null;
}

export interface Evidence {
  handle: string;
  text: string;
  content_hash: string;
  locator: Record<string, unknown>;
  locator_label: string;
  heading_path: string[];
  source: EvidenceSource;
  provenance: EvidenceProvenance;
  context: { previous_excerpt: string | null; next_excerpt: string | null };
  children: EvidenceChild[];
  highlight: EvidenceHighlight | null;
}

export interface Tombstone {
  handle: string;
  source_code: string;
  title: string;
  version: number;
  deleted_at: string;
}

export interface SearchAnchor {
  child_id: string;
  lane: "dense" | "lexical";
  char_start: number;
  char_end: number;
}

/** Snippet offsets count Unicode code points (see lib/highlight.ts). */
export interface SearchSnippet {
  text: string;
  mark_start: number;
  mark_end: number;
  truncated_left: boolean;
  truncated_right: boolean;
}

export interface SearchScores {
  rrf: number;
  rerank: number | null;
  fused_rank: number;
  lanes: { dense?: number; lexical?: number };
}

export interface SearchItem {
  rank: number;
  handle: string;
  locator_label: string;
  source_code: string;
  source_title: string;
  source_type: string;
  source_class: string;
  anchor: SearchAnchor;
  snippet: SearchSnippet;
  scores: SearchScores;
}

export interface SearchResponse {
  query: string;
  mode: string;
  items: SearchItem[];
  flags: string[];
  trace_id: string | null;
  timings_ms: Record<string, number>;
}

export interface SearchParams {
  q: string;
  mode: SearchMode;
  k?: number;
  sourceClasses?: readonly SourceClass[];
  sources?: readonly string[];
  maxConfidentiality?: Confidentiality;
}

/* ---------------------------------------------------------------------------------------------
 * Phase 3: conversations, grounded-answer runs and the SSE run stream.
 * ------------------------------------------------------------------------------------------- */

/** Citation card stored with a final answer; `handle` is canonical (never a run-local alias). */
export interface CitationCard {
  handle: string;
  source_code: string;
  source_title: string;
  source_class: string;
  source_type: string;
  locator_label: string;
  anchor_child_id: string | null;
  char_start: number | null;
  char_end: number | null;
  parent_content_hash: string | null;
}

export type MessageRole = "user" | "assistant";
export type MessageStatus = "complete" | "incomplete" | "failed" | "redacted";

export interface ChatMessage {
  message_id: string;
  role: MessageRole;
  content: string;
  citations: CitationCard[] | null;
  /** Raw section payload; parse with lib/answer-sections.ts (shape varies by outcome). */
  sections: unknown;
  status: MessageStatus;
  run_id: string | null;
  created_at: string;
}

export interface CreateConversationInput {
  title?: string;
  persona?: string;
}

export interface CreateConversationResult {
  conversation_id: string;
}

/** `auto` is routed deterministically by the server; an explicit `standard`/`research` always wins. */
export const RUN_MODES = ["auto", "standard", "research"] as const;
export type RunMode = (typeof RUN_MODES)[number];

export interface StartRunInput {
  question: string;
  mode?: RunMode;
}

export interface StartRunResult {
  run_id: string;
  /** Path (with a short-lived `st` token) to open with EventSource against API_BASE_URL. */
  stream_url: string;
}

export interface CancelRunResult {
  run_id: string;
  cancel_requested: boolean;
  status: string;
}

/**
 * Type declarations for `tasnim-client.mjs` — the Tasnim Web V1
 * read-only API client (PCM-20.6.4, Track B). Mirrors the Python SDK
 * 1:1. See `docs/PCM-20.6.4-INTEGRATION.md` for the full contract.
 *
 * Usage:
 *   import TasnimClient from "./tasnim-client.mjs";
 *   // or with `declare module` / `paths` in your tsconfig.
 */

export const API_PREFIX: string;
export const CANONICAL_BASE_URL: string;
export const RATE_LIMITS: { search: number; read: number; window: string };
export const DEFAULT_TIMEOUT: number;
export const DEFAULT_USER_AGENT: string;

// ---------------------------------------------------------------------------
// errors
// ---------------------------------------------------------------------------

/** Transport/protocol failure (DNS, connection refused, timeout, non-JSON). */
export class TasnimClientError extends Error {}

/** A well-formed API error envelope (4xx/5xx from the server). */
export class TasnimAPIError extends TasnimClientError {
  /** HTTP status code. */
  readonly status: number;
  /** Stable machine code, e.g. `"VOLUME_NOT_FOUND"`, `"RATE_LIMITED"`. */
  readonly code: string;
  /** Short human title (Persian). */
  readonly title: string | null;
  /** Optional details object (e.g. `{ limit: 30, window: "60s" }`). */
  readonly details: Record<string, unknown> | null;
  /** `req_...` correlation id for support. */
  readonly requestId: string | null;
  /** `https://tasnim.ai.ismc.ir/errors/<code-slug>`. */
  readonly type: string | null;
  /** Integer seconds, set on 429 (from `Retry-After`). */
  readonly retryAfter: number | null;
  /** The raw error envelope. */
  readonly body: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// response objects
// ---------------------------------------------------------------------------

/** One successful API call: `data` (the payload) + `meta`. */
export class TasnimResponse<T = any> {
  constructor(data: T, meta: TasnimMeta | null,
              opts?: { status?: number; etag?: string | null;
                       cacheControl?: string | null; fromCache?: boolean });
  readonly data: T;
  readonly meta: TasnimMeta;
  readonly status: number;
  readonly etag: string | null;
  readonly cacheControl: string | null;
  /** True when the response was served from the in-memory ETag cache (304). */
  fromCache: boolean;
  readonly requestId: string | null;
  readonly nextPageToken: string | null;
  readonly readmodel: TasnimReadmodel;
  toString(): string;
}

export interface TasnimMeta {
  request_id: string;
  readmodel?: TasnimReadmodel;
  generated_at?: string;
  next_page_token?: string | null;
}

export interface TasnimReadmodel {
  version: string;
  content_sha256: string;
  db_sha256?: string;
}

/** The `/pages/{item_index}` payload with convenience getters.
 * The raw snake_case payload keys are also copied onto the instance, so
 * `page.item_index` and `page.itemIndex` both work. */
export class Page {
  constructor(raw: Record<string, any>);
  /** The raw snake_case payload. */
  readonly raw: Record<string, any>;
  readonly itemIndex: number | null;
  readonly pageId: string | null;
  readonly dupRank: number | null;
  readonly barg: number | null;
  readonly text: string | null;
  readonly charCount: number | null;
  readonly recordClass: string | null;
  readonly volumeId: string | null;
  readonly volumeNo: number | null;
  readonly headingText: string | null;
  readonly qualityStatus: string | null;
  readonly flags: string[];
  readonly truncatedAtSource: boolean;
  readonly canonicalUrl: string | null;
  readonly sourceUrl: string | null;
  readonly capturedAt: string | null;
  readonly sourcePageId: string | null;
  /** `null` when the next neighbor is absent (end of corpus). */
  readonly nextItemIndex: number | null;
  /** `null` when the previous neighbor is absent (beginning of corpus). */
  readonly previousItemIndex: number | null;
  // raw snake_case payload keys (copied onto the instance):
  item_index: number;
  page_id: string;
  dup_rank: number;
  barg: number | null;
  visible_content: { text: string; char_count: number; record_class: string };
  volume: { volume_id: string; volume_no: number | null };
  heading: { text: string | null } | null;
  quality: { status: string; flags: string[]; truncated_at_source?: boolean };
  reference: { canonical_url: string; source_url?: string | null };
  metadata: Record<string, unknown>;
  next_page_reference: TasnimPageReference | null;
  previous_page_reference: TasnimPageReference | null;
  rag_status: Record<string, unknown>;
}

/** Gap-aware navigation reference. */
export interface TasnimPageReference {
  item_index: number;
  page_id: string | null;
  exists: boolean;
  gap_before: number;
  in_missing_range?: [number, number];
  next_available_item_index?: number | null;
  prev_available_item_index?: number | null;
  gap?: TasnimPageReference | null;
  reason?: string | null;
}

/** The `/topics/{topic_id}` payload with convenience getters. */
export class TopicDetail {
  constructor(raw: Record<string, any>);
  readonly raw: Record<string, any>;
  readonly topicId: string | null;
  readonly displayText: string | null;
  readonly normalizedText: string | null;
  readonly pageCount: number | null;
  readonly volumeCount: number | null;
  readonly occurrencesTotal: number | null;
  readonly occurrences: TasnimOccurrence[];
  readonly samplePages: unknown[];
  readonly firstItemIndex: number | null;
  readonly firstPageId: string | null;
  readonly parentTopic: string | null;
  topic_id: string;
  display_text: string;
  normalized_text: string;
  page_count: number;
  volume_count: number;
  occurrences_total: number;
  occurrences_list?: TasnimOccurrence[];
  sample_pages?: unknown[];
  first_item_index: number;
  first_page_id: string;
  parent_topic?: string | null;
}

export interface TasnimOccurrence {
  item_index: number;
  page_id: string;
  is_heading_page?: boolean;
  [k: string]: unknown;
}

// ---------------------------------------------------------------------------
// options
// ---------------------------------------------------------------------------

export interface TasnimClientOptions {
  /** Server root (default: the public V1 host). */
  baseUrl?: string;
  /** Per-request timeout in seconds (default 30). */
  timeout?: number;
  /** On 429, sleep `Retry-After` (capped) and retry. Default true. */
  rateLimitBackoff?: boolean;
  /** Extra attempts after the first on 429. Default 3. */
  maxRetries?: number;
  /** Cap for a single backoff sleep in seconds. Default 65. */
  maxBackoffS?: number;
  /** In-memory `If-None-Match` cache. Default true. */
  etagCache?: boolean;
  /** Injectable clock (tests). */
  clock?: () => number;
  /** Injectable `(seconds) => Promise|void` for tests. */
  sleep?: (seconds: number) => void | Promise<void>;
  /** Sent as `User-Agent`. */
  userAgent?: string;
  /** Injectable `fetch` replacement (tests). */
  fetchImpl?: typeof fetch;
}

export interface ListOptions {
  limit?: number;
  offset?: number;
  pageToken?: string;
}

// ---------------------------------------------------------------------------
// the client
// ---------------------------------------------------------------------------

export class TasnimClient {
  constructor(opts?: TasnimClientOptions);
  readonly root: string;
  readonly timeout: number;

  /** GET /catalog — work/edition identity + live counts + coverage. */
  getCatalog(): Promise<TasnimResponse>;
  /** GET /volumes — paginated volume list. */
  listVolumes(
    opts?: ListOptions & { sort?: "volume_no" | "page_count" }
  ): Promise<TasnimResponse>;
  /** Walk all /volumes pages (token chain). */
  iterVolumes(
    opts?: { limit?: number; sort?: "volume_no" | "page_count" }
  ): AsyncIterable<Record<string, unknown>>;
  /** GET /volumes/{volume_id} — full volume record. */
  getVolume(volumeId: string): Promise<TasnimResponse>;
  /** GET /surahs — always 503 in V1. */
  getSurahs(): Promise<TasnimResponse>;
  /** GET /surahs/{surah_id} — always 503 in V1. */
  getSurah(surahId: string): Promise<TasnimResponse>;
  /** GET /topics — paginated topic list. */
  listTopics(
    opts?: ListOptions & {
      q?: string; minPages?: number; sort?: "page_count" | "name";
    }
  ): Promise<TasnimResponse>;
  /** Walk all /topics pages (token chain). */
  iterTopics(
    opts?: { limit?: number; q?: string; minPages?: number;
             sort?: "page_count" | "name" }
  ): AsyncIterable<Record<string, unknown>>;
  /** GET /topics/{topic_id} → TopicDetail. */
  getTopic(topicId: string): Promise<TopicDetail>;
  /** GET /pages/{item_index} → Page. */
  getPage(itemIndex: number, dupRank?: number): Promise<Page>;
  /** Walk existing `item_index` in `[min, max]` (gap-aware). */
  iterPages(
    itemIndexMin: number, itemIndexMax: number,
    opts?: { dupRank?: number; onMissing?: "skip" | "raise" }
  ): AsyncIterable<Page>;
  /** GET /pages/{item_index}/neighbors. */
  getPageNeighbors(itemIndex: number): Promise<TasnimResponse>;
  /** GET /search — full-text search. */
  search(
    q: string,
    opts?: { volumeId?: string; sort?: string; limit?: number;
             offset?: number; pageToken?: string }
  ): Promise<TasnimResponse>;
  /** GET /statistics. */
  getStatistics(): Promise<TasnimResponse>;
  /** GET /health. */
  getHealth(): Promise<TasnimResponse>;
  /** Drop the in-memory ETag cache. */
  clearEtagCache(): void;
  toString(): string;
}

export default TasnimClient;

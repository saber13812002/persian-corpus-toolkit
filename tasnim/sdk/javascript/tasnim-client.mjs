// tasnim-client — the Tasnim Web V1 read-only API client (JavaScript).
//
// Zero dependencies: ES module, global `fetch` (Node 18+ / all modern
// browsers). Mirrors 1:1 the Python SDK (`tasnim/sdk/python`) — same 12
// endpoints, same envelope, same error semantics, same 429 backoff and
// ETag-cache behavior. See `tasnim.sdk.d.ts` for the TypeScript types
// and `docs/PCM-20.6.4-INTEGRATION.md` for the full contract.
//
// Contract (PCM-20.6.4, spec §5 — mirrored from `tasnim/web/api.py`):
//
// * Base path `/api/v1/tasnim` — 12 read-only endpoints, JSON, UTF-8.
// * Envelope: `{ data, meta: { request_id, readmodel, generated_at,
//   next_page_token? } }`.
// * Errors: RFC-7807-ish `{ type, title, status, code, message, details,
//   request_id }` → thrown as `TasnimAPIError`.
// * Rate limits: 30 search req/min, 120 read req/min per IP; 429 with a
//   `Retry-After` header. The client backs off automatically
//   (`rateLimitBackoff`) and exposes the parsed error either way.
// * Pagination: `limit` (default 50 / 20 for search, max 200) + `offset`
//   OR opaque `pageToken`; `meta.nextPageToken` present while more pages
//   remain. `iter*` async generators walk the chain to exhaustion.
// * Caching: stable endpoints send an ETag; the in-memory cache
//   (`etagCache=true`) sends `If-None-Match` and returns the cached
//   response on 304 (`fromCache=true`). Search is `no-store` and never
//   hits 304.
//
// The public production base URL is `https://tasnim.ai.ismc.ir`
// (canonical, for citations); any V1 instance works — pass its root.

export const API_PREFIX = "/api/v1/tasnim";
export const CANONICAL_BASE_URL = "https://tasnim.ai.ismc.ir";

// Rate limits (server-side, per IP per wall-clock minute) — informational;
// the client never enforces them itself, it only reacts to 429.
export const RATE_LIMITS = { search: 30, read: 120, window: "60s" };

export const DEFAULT_TIMEOUT = 30; // seconds
export const DEFAULT_USER_AGENT = "tasnim-client-js/1.0";

// ---------------------------------------------------------------------------
// errors
// ---------------------------------------------------------------------------

/** Transport/protocol failure (DNS, connection refused, timeout, non-JSON). */
export class TasnimClientError extends Error {
  constructor(message) {
    super(message);
    this.name = "TasnimClientError";
  }
}

/** A well-formed API error envelope (4xx/5xx from the server).
 *
 * Attributes mirror the envelope:
 *
 * * `status`      — HTTP status code
 * * `code`        — stable machine code, e.g. `"VOLUME_NOT_FOUND"`
 * * `title`       — short human title
 * * `details`     — optional object (e.g. `{ limit: 30, ... }`)
 * * `requestId`   — `req_...` correlation id for support
 * * `type`        — `https://tasnim.ai.ismc.ir/errors/<code-slug>`
 * * `retryAfter`  — integer seconds, set on 429 (from `Retry-After`)
 * * `body`        — the raw error envelope
 *
 * `Error.message` carries `"<status> <code>: <detailed message>"`. */
export class TasnimAPIError extends TasnimClientError {
  constructor({ status, code, title = null, message = null,
                details = null, requestId = null, type = null,
                retryAfter = null, body = null }) {
    super(`${status} ${code}: ${message || title || ""}`);
    this.name = "TasnimAPIError";
    this.status = status;
    this.code = code;
    this.title = title;
    this.details = details;
    this.requestId = requestId;
    this.type = type;
    this.retryAfter = retryAfter;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// response objects
// ---------------------------------------------------------------------------

/** One successful API call: `data` (the payload) + `meta`. */
export class TasnimResponse {
  constructor(data, meta,
              { status = 200, etag = null, cacheControl = null,
                fromCache = false } = {}) {
    this.data = data;
    this.meta = meta || {};
    this.status = status;
    this.etag = etag;
    this.cacheControl = cacheControl;
    this.fromCache = fromCache;
  }

  get requestId() { return this.meta.request_id ?? null; }
  get nextPageToken() { return this.meta.next_page_token ?? null; }
  get readmodel() { return this.meta.readmodel || {}; }

  toString() {
    return `TasnimResponse(status=${this.status}, requestId=${this.requestId}, fromCache=${this.fromCache})`;
  }
}

/** Copy the payload's keys onto `obj` as own, enumerable data
 * properties. Uses `Object.defineProperty` (not plain assignment) so a
 * key that collides with a getter-only accessor on the prototype
 * (e.g. `barg`) cannot throw in strict mode. */
function _copyRaw(obj, payload) {
  for (const k of Object.keys(payload)) {
    Object.defineProperty(obj, k, {
      value: payload[k],
      writable: true, enumerable: true, configurable: true,
    });
  }
}

/** The `/pages/{item_index}` payload, with convenience getters.
 *
 * The raw payload keys (snake_case) are copied onto the instance as well,
 * so `page.item_index` and `page.itemIndex` both work — mirroring the
 * Python `Page`, which is a `dict` subclass. Gap-aware navigation:
 * `nextItemIndex` / `previousItemIndex` are `null` when the neighbor is
 * absent (beginning / end of corpus); the full reference objects (with
 * `in_missing_range`, `gap_before`, ...) are in
 * `next_page_reference` / `previous_page_reference`. */
export class Page {
  constructor(raw) {
    const payload = (raw && typeof raw === "object") ? raw : {};
    _copyRaw(this, payload); // snake_case keys, like the Python dict
    this._raw = payload;
  }

  get raw() { return this._raw; }
  get itemIndex() { return this._raw.item_index ?? null; }
  get pageId() { return this._raw.page_id ?? null; }
  get dupRank() { return this._raw.dup_rank ?? null; }
  get barg() { return this._raw.barg ?? null; }
  get text() { return (this._raw.visible_content || {}).text ?? null; }
  get charCount() { return (this._raw.visible_content || {}).char_count ?? null; }
  get recordClass() { return (this._raw.visible_content || {}).record_class ?? null; }
  get volumeId() { return (this._raw.volume || {}).volume_id ?? null; }
  get volumeNo() { return (this._raw.volume || {}).volume_no ?? null; }
  get headingText() { return (this._raw.heading || {}).text ?? null; }
  get qualityStatus() { return (this._raw.quality || {}).status ?? null; }
  get flags() { return (this._raw.quality || {}).flags || []; }
  get truncatedAtSource() {
    return Boolean((this._raw.quality || {}).truncated_at_source);
  }
  get canonicalUrl() { return (this._raw.reference || {}).canonical_url ?? null; }
  get sourceUrl() { return (this._raw.reference || {}).source_url ?? null; }
  get capturedAt() { return (this._raw.metadata || {}).captured_at ?? null; }
  get sourcePageId() { return (this._raw.metadata || {}).source_page_id ?? null; }
  get nextItemIndex() {
    const ref = this._raw.next_page_reference || {};
    return ref.exists ? ref.item_index : null;
  }
  get previousItemIndex() {
    const ref = this._raw.previous_page_reference || {};
    return ref.exists ? ref.item_index : null;
  }
}

/** The `/topics/{topic_id}` payload, with convenience getters.
 * `occurrences` is paginated server-side: the list is `occurrences` and
 * the total is `occurrencesTotal`. */
export class TopicDetail {
  constructor(raw) {
    const payload = (raw && typeof raw === "object") ? raw : {};
    _copyRaw(this, payload);
    this._raw = payload;
  }

  get raw() { return this._raw; }
  get topicId() { return this._raw.topic_id ?? null; }
  get displayText() { return this._raw.display_text ?? null; }
  get normalizedText() { return this._raw.normalized_text ?? null; }
  get pageCount() { return this._raw.page_count ?? null; }
  get volumeCount() { return this._raw.volume_count ?? null; }
  get occurrencesTotal() { return this._raw.occurrences_total ?? null; }
  get occurrences() { return this._raw.occurrences || []; }
  get samplePages() { return this._raw.sample_pages || []; }
  get firstItemIndex() { return this._raw.first_item_index ?? null; }
  get firstPageId() { return this._raw.first_page_id ?? null; }
  get parentTopic() { return this._raw.parent_topic ?? null; }
}

// ---------------------------------------------------------------------------
// the client
// ---------------------------------------------------------------------------

/** Read-only client for the Tasnim Web V1 API.
 *
 * Options (all optional):
 *
 * * `baseUrl`       — server root, e.g. `"https://tasnim.ai.ismc.ir"` or
 *   `"http://127.0.0.1:5071"`. A trailing `/api/v1/tasnim` (with or
 *   without slash) is allowed and not doubled. Default: the public host.
 * * `timeout`       — per-request timeout in seconds (default 30).
 * * `rateLimitBackoff` — on 429, sleep `Retry-After` (capped) and retry,
 *   up to `maxRetries` times; when false, the `TasnimAPIError`
 *   (code `RATE_LIMITED`) is thrown immediately.
 * * `maxRetries`    — how many extra attempts after the first on 429.
 * * `maxBackoffS`   — cap for a single backoff sleep (the server's
 *   `Retry-After` can be up to 60 s).
 * * `etagCache`     — in-memory `If-None-Match` cache; on 304 the
 *   previously returned response is reused (`fromCache=true`).
 * * `clock`         — injectable, for tests (ignored on the hot path).
 * * `sleep`         — injectable `(seconds) => Promise|void` for tests
 *   (default: real `setTimeout`).
 * * `userAgent`     — sent as `User-Agent`.
 * * `fetchImpl`     — injectable `fetch` replacement (tests).
 */
export class TasnimClient {
  constructor({ baseUrl = CANONICAL_BASE_URL, timeout = DEFAULT_TIMEOUT,
                rateLimitBackoff = true, maxRetries = 3, maxBackoffS = 65,
                etagCache = true, clock = null, sleep = null,
                userAgent = DEFAULT_USER_AGENT, fetchImpl = null } = {}) {
    if (!baseUrl) {
      throw new Error("baseUrl is required");
    }
    let root = String(baseUrl).replace(/\/+$/, "");
    if (root.endsWith(API_PREFIX)) {
      root = root.slice(0, -API_PREFIX.length).replace(/\/+$/, "");
    }
    this.root = root;
    this.timeout = timeout;
    this.rateLimitBackoff = rateLimitBackoff;
    this.maxRetries = maxRetries;
    this.maxBackoffS = maxBackoffS;
    this.etagCache = etagCache;
    this._etagStore = new Map(); // url -> { response, etag }
    this._clock = clock || (() => Date.now());
    this._sleep = sleep || ((s) => new Promise((r) => setTimeout(r, s * 1000)));
    this._userAgent = userAgent;
    this._fetchImpl = fetchImpl || (typeof fetch !== "undefined" ? fetch : null);
    if (!this._fetchImpl) {
      throw new Error("no global fetch available (Node 18+ required)");
    }
  }

  // -- public API: the 12 endpoints ---------------------------------------

  /** GET /catalog — work/edition identity + live counts + coverage.
   * ETag-cached (strong), `Cache-Control: public, max-age=60`. */
  getCatalog() {
    return this._request("GET", "/catalog", null, true);
  }

  /** GET /volumes — paginated volume list. `sort`: `"volume_no"`
   * (default) or `"page_count"`. Use `iterVolumes` to walk all pages. */
  listVolumes({ limit = 50, offset = undefined, pageToken = undefined,
                sort = "volume_no" } = {}) {
    const params = { limit, sort };
    this._addPaging(params, offset, pageToken);
    return this._request("GET", "/volumes", params, true);
  }

  /** Yield volume dicts across all /volumes pages (token chain). */
  async *iterVolumes({ limit = 50, sort = "volume_no" } = {}) {
    let token = null;
    for (;;) {
      const r = await this.listVolumes({ limit, sort, pageToken: token });
      for (const item of (r.data.items || [])) yield item;
      token = r.nextPageToken;
      if (!token) return;
    }
  }

  /** GET /volumes/{volume_id} — full volume record. 404
   * `VOLUME_NOT_FOUND` if the id is not in the read model. */
  getVolume(volumeId) {
    return this._request("GET", "/volumes/" + TasnimClient._quote(volumeId),
                         null, true);
  }

  /** GET /surahs — always 503 `SURAH_INDEX_NOT_SUPPORTED` in V1 (honest
   * unavailability; see the error `details.evidence`). */
  getSurahs() {
    return this._request("GET", "/surahs", null, false);
  }

  /** GET /surahs/{surah_id} — always 503 in V1 (as above). */
  getSurah(surahId) {
    return this._request("GET", "/surahs/" + TasnimClient._quote(surahId),
                         null, false);
  }

  /** GET /topics — paginated topic list. `q` filters by normalized-text
   * *prefix*; `minPages` filters `page_count >= n`; `sort`:
   * `"page_count"` (default) or `"name"`. Use `iterTopics` to walk all
   * pages (note: the full chain can be long — prefer one page). */
  listTopics({ limit = 50, offset = undefined, pageToken = undefined,
               q = undefined, minPages = undefined,
               sort = "page_count" } = {}) {
    const params = { limit, sort };
    if (q !== undefined && q !== null) params.q = q;
    if (minPages !== undefined && minPages !== null) {
      params.min_pages = minPages;
    }
    this._addPaging(params, offset, pageToken);
    return this._request("GET", "/topics", params, true);
  }

  /** Yield topic dicts across all /topics pages (token chain). */
  async *iterTopics({ limit = 50, q = undefined, minPages = undefined,
                      sort = "page_count" } = {}) {
    let token = null;
    for (;;) {
      const r = await this.listTopics({ limit, q, minPages, sort,
                                        pageToken: token });
      for (const item of (r.data.items || [])) yield item;
      token = r.nextPageToken;
      if (!token) return;
    }
  }

  /** GET /topics/{topic_id} → `TopicDetail`. 404 `TOPIC_NOT_FOUND`. */
  async getTopic(topicId) {
    const r = await this._request(
      "GET", "/topics/" + TasnimClient._quote(topicId), null, true);
    return new TopicDetail(r.data);
  }

  /** GET /pages/{item_index} → `Page` (the heart of the contract:
   * gap-aware next/prev references, quality, duplicates, provenance
   * metadata, `rag_status`). 404 `PAGE_NOT_FOUND` carries
   * `details.in_missing_range` and a nearest-available `suggestion`. */
  async getPage(itemIndex, dupRank = 0) {
    const params = {};
    if (dupRank) params.dup_rank = dupRank;
    const r = await this._request(
      "GET", "/pages/" + Number(itemIndex), params, true);
    return new Page(r.data);
  }

  /** Yield `Page` for each existing `item_index` in `[min, max]`.
   * Missing indexes (gaps) are skipped by default (`onMissing: "skip"`)
   * — the corpus has real gaps and gap-awareness is the point; with
   * `"raise"` a `PAGE_NOT_FOUND` propagates. Note: each page is one
   * read-class request (120/min per IP); for big ranges consider the
   * corpus dumps instead of the live API. */
  async *iterPages(itemIndexMin, itemIndexMax,
                   { dupRank = 0, onMissing = "skip" } = {}) {
    for (let ii = Number(itemIndexMin); ii <= Number(itemIndexMax); ii += 1) {
      try {
        yield await this.getPage(ii, dupRank);
      } catch (e) {
        if (e instanceof TasnimAPIError && e.code === "PAGE_NOT_FOUND"
            && onMissing === "skip") continue;
        throw e;
      }
    }
  }

  /** GET /pages/{item_index}/neighbors — gap-aware prev/next reference
   * objects + `missing_nearby` ranges. */
  getPageNeighbors(itemIndex) {
    return this._request(
      "GET", "/pages/" + Number(itemIndex) + "/neighbors", null, true);
  }

  /** GET /search — full-text (Persian-stemmed) search. `q` must be
   * 2..64 chars; 3+ tokens switch to *estimated* results
   * (`total === -1` and `data.estimated === true`). Zero hits (exact
   * mode) return `suggestions` (top topics). Responses are `no-store`
   * (weak ETag) — not etag-cached. Search-class rate limit: 30/min. */
  search(q, { volumeId = undefined, sort = "relevance", limit = 20,
              offset = undefined, pageToken = undefined } = {}) {
    const params = { q, limit, sort };
    if (volumeId !== undefined && volumeId !== null) {
      params.volume_id = volumeId;
    }
    this._addPaging(params, offset, pageToken);
    return this._request("GET", "/search", params, false);
  }

  /** GET /statistics — live GROUP BY counters with written definitions
   * (pages_by_class, quality_status, item_index incl. missing ranges,
   * text_length percentiles, topics, surah). */
  getStatistics() {
    return this._request("GET", "/statistics", null, true);
  }

  /** GET /health — readmodel identity + db quick check + uptime.
   * Exempt from rate limiting (safe for probes). */
  getHealth() {
    return this._request("GET", "/health", null, false);
  }

  // -- plumbing ------------------------------------------------------------

  static _quote(value) {
    return encodeURIComponent(String(value));
  }

  _addPaging(params, offset, pageToken) {
    if (pageToken !== undefined && pageToken !== null) {
      params.page_token = pageToken;
    } else if (offset !== undefined && offset !== null) {
      params.offset = offset;
    }
  }

  _url(path, params) {
    let url = this.root + API_PREFIX + path;
    if (params) {
      const sp = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) sp.set(k, String(v));
      }
      const q = sp.toString();
      if (q) url += "?" + q;
    }
    return url;
  }

  async _request(method, path, params = null, useEtag = false) {
    const url = this._url(path, params);
    const headers = {
      "User-Agent": this._userAgent,
      "Accept": "application/json",
    };
    if (useEtag && this.etagCache) {
      const cached = this._etagStore.get(url);
      if (cached) headers["If-None-Match"] = cached.etag;
    }
    const { status, headers: resHeaders, bodyText } =
      await this._http(method, url, headers);
    const obj = TasnimClient._parse(bodyText, url);
    if (status === 304 && useEtag && this.etagCache) {
      const cached = this._etagStore.get(url);
      if (cached) {
        cached.response.fromCache = true;
        return cached.response;
      }
    }
    if (status >= 400) {
      throw this._apiError(status, resHeaders, obj, bodyText, url);
    }
    const isEnvelope = obj && typeof obj === "object"
      && !Array.isArray(obj) && "data" in obj;
    const resp = new TasnimResponse(
      isEnvelope ? obj.data : obj,
      (isEnvelope && obj.meta) || null,
      { status, etag: resHeaders.get("ETag"),
        cacheControl: resHeaders.get("Cache-Control") });
    if (status === 200 && useEtag && this.etagCache) {
      const etag = resHeaders.get("ETag");
      if (etag) this._etagStore.set(url, { response: resp, etag });
    }
    return resp;
  }

  /** One GET (with 429 backoff). Returns `{status, headers, bodyText}`.
   * 429 is retried (capped Retry-After sleep) while `rateLimitBackoff`
   * and attempts remain; otherwise the error is raised by the caller.
   * Transport failures (DNS, refused, timeout) become
   * `TasnimClientError`. */
  async _http(method, url, headers) {
    let attempt = 0;
    for (;;) {
      const controller = typeof AbortController !== "undefined"
        ? new AbortController() : null;
      const timeoutMs = Number(this.timeout) * 1000;
      const timer = (controller && Number.isFinite(timeoutMs) && timeoutMs > 0)
        ? setTimeout(() => controller.abort(), timeoutMs) : null;
      let res;
      try {
        res = await this._fetchImpl(url, {
          method, headers,
          signal: controller ? controller.signal : undefined,
        });
      } catch (e) {
        if (timer) clearTimeout(timer);
        const name = e && e.name;
        if (name === "AbortError" || name === "TimeoutError") {
          throw new TasnimClientError(
            `transport error on ${url}: timeout after ${this.timeout}s`);
        }
        throw new TasnimClientError(
          `transport error on ${url}: ${(e && e.message) || e}`);
      }
      if (timer) clearTimeout(timer);

      if (res.status === 429 && this.rateLimitBackoff
          && attempt < this.maxRetries) {
        const retryAfter = res.headers.get("Retry-After");
        let wait = null;
        if (retryAfter) {
          const v = Number.parseFloat(retryAfter);
          if (Number.isFinite(v)) wait = v;
        }
        if (wait == null) {
          wait = Math.min(this.maxBackoffS, Math.pow(1.5, attempt));
        }
        wait = Math.max(1.0, Math.min(wait, this.maxBackoffS));
        await this._sleep(wait);
        attempt += 1;
        continue;
      }

      let bodyText = "";
      try { bodyText = await res.text(); } catch (e) { bodyText = ""; }
      return { status: res.status, headers: res.headers, bodyText };
    }
  }

  static _parse(bodyText, url) {
    if (!bodyText) return null;
    try {
      return JSON.parse(bodyText);
    } catch (e) {
      throw new TasnimClientError(
        `non-JSON response from ${url}: ${e.message}`);
    }
  }

  _apiError(status, resHeaders, obj, bodyText, url) {
    let retryAfter = null;
    const ra = resHeaders ? resHeaders.get("Retry-After") : null;
    if (ra && /^\d+$/.test(String(ra).trim())) {
      retryAfter = parseInt(String(ra).trim(), 10);
    }
    if (obj && typeof obj === "object" && !Array.isArray(obj)
        && "code" in obj && "status" in obj) {
      return new TasnimAPIError({
        status: ("status" in obj && obj.status !== null) ? obj.status : status,
        code: obj.code,
        title: obj.title ?? null,
        message: obj.message ?? null,
        details: obj.details ?? null,
        requestId: obj.request_id ?? null,
        type: obj.type ?? null,
        retryAfter,
        body: obj,
      });
    }
    return new TasnimClientError(
      `HTTP ${status} from ${url}: ${String(bodyText || "").slice(0, 200)}`);
  }

  // -- misc ----------------------------------------------------------------

  clearEtagCache() {
    this._etagStore.clear();
  }

  toString() {
    return `TasnimClient(base_url=${JSON.stringify(this.root)})`;
  }
}

export default TasnimClient;

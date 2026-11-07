# -*- coding: utf-8 -*-
"""tasnim_client.client — the Tasnim Web V1 read-only API client.

Standard library only (``urllib.request``). Chosen over ``requests`` on
purpose: the corpus toolchain is dependency-light and this SDK must work
in the same environment as the offline pipelines.

Contract (PCM-20.6.4, spec §5 — mirrored 1:1 from ``tasnim/web/api.py``):

* Base path ``/api/v1/tasnim`` — 12 read-only endpoints, JSON, UTF-8.
* Envelope: ``{"data": ..., "meta": {"request_id", "readmodel",
  "generated_at", "next_page_token"?}}``.
* Errors: RFC-7807-ish ``{"type", "title", "status", "code", "message",
  "details", "request_id"}`` → raised as :class:`TasnimAPIError`.
* Rate limits: 30 search req/min, 120 read req/min per IP; 429 with
  ``Retry-After`` header. The client backs off automatically (see
  ``rate_limit_backoff``) and exposes the parsed error either way.
* Pagination: ``limit`` (default 50 / 20 for search, max 200) +
  ``offset`` OR opaque ``page_token``; ``meta.next_page_token`` present
  while more pages remain. ``iter_*`` generators walk the chain.
* Caching: stable endpoints send ETag; a client-side in-memory ETag
  cache (``etag_cache=True``) sends ``If-None-Match`` and returns the
  cached response on 304.

The public production base URL is ``https://tasnim.ai.ismc.ir``
(canonical, for citations); any V1 instance works — pass its root.
"""
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

API_PREFIX = "/api/v1/tasnim"

# Rate limits (server-side, per IP per wall-clock minute) — informational;
# the client never enforces them itself, it only reacts to 429.
RATE_LIMITS = {"search": 30, "read": 120, "window": "60s"}

DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "tasnim-client-py/1.0"


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class TasnimClientError(Exception):
    """Transport/protocol failure (DNS, timeout, non-JSON body, ...)."""


class TasnimAPIError(TasnimClientError):
    """A well-formed API error envelope (4xx/5xx from the server).

    Attributes mirror the envelope:

    * ``status``      — HTTP status code (int)
    * ``code``        — stable machine code, e.g. ``"VOLUME_NOT_FOUND"``
    * ``title``       — short human title
    * ``message``     — detailed (Persian) message
    * ``details``     — optional dict (e.g. ``{"limit": 30, ...}``)
    * ``request_id``  — ``req_...`` correlation id for support
    * ``type``        — ``https://tasnim.ai.ismc.ir/errors/<code-slug>``
    * ``retry_after`` — int seconds, set on 429 (from ``Retry-After``)
    """

    def __init__(self, status, code, title=None, message=None, details=None,
                 request_id=None, type_=None, retry_after=None, body=None):
        self.status = status
        self.code = code
        self.title = title
        self.message = message
        self.details = details
        self.request_id = request_id
        self.type = type_
        self.retry_after = retry_after
        self.body = body
        super().__init__("%s %s: %s" % (status, code, message or title or ""))

    def __repr__(self):
        return ("TasnimAPIError(status=%r, code=%r, request_id=%r)"
                % (self.status, self.code, self.request_id))


# ---------------------------------------------------------------------------
# response objects
# ---------------------------------------------------------------------------

class TasnimResponse:
    """One successful API call: ``data`` (the payload) + ``meta``."""

    def __init__(self, data, meta, status=200, etag=None,
                 cache_control=None, from_cache=False):
        self.data = data
        self.meta = meta or {}
        self.status = status
        self.etag = etag
        self.cache_control = cache_control
        self.from_cache = from_cache

    @property
    def request_id(self):
        return self.meta.get("request_id")

    @property
    def next_page_token(self):
        return self.meta.get("next_page_token")

    @property
    def readmodel(self):
        return self.meta.get("readmodel") or {}

    def __repr__(self):
        return ("TasnimResponse(status=%r, request_id=%r, from_cache=%r)"
                % (self.status, self.request_id, self.from_cache))


class Page(dict):
    """The ``/pages/{item_index}`` payload as a dict, with convenience
    properties (see integration guide §"page object")."""

    @property
    def item_index(self):
        return self.get("item_index")

    @property
    def page_id(self):
        return self.get("page_id")

    @property
    def dup_rank(self):
        return self.get("dup_rank")

    @property
    def barg(self):
        return self.get("barg")

    @property
    def text(self):
        return (self.get("visible_content") or {}).get("text")

    @property
    def char_count(self):
        return (self.get("visible_content") or {}).get("char_count")

    @property
    def record_class(self):
        return (self.get("visible_content") or {}).get("record_class")

    @property
    def volume_id(self):
        return (self.get("volume") or {}).get("volume_id")

    @property
    def volume_no(self):
        return (self.get("volume") or {}).get("volume_no")

    @property
    def heading_text(self):
        return (self.get("heading") or {}).get("text")

    @property
    def quality_status(self):
        return (self.get("quality") or {}).get("status")

    @property
    def flags(self):
        return (self.get("quality") or {}).get("flags") or []

    @property
    def truncated_at_source(self):
        return bool((self.get("quality") or {}).get("truncated_at_source"))

    @property
    def canonical_url(self):
        return (self.get("reference") or {}).get("canonical_url")

    @property
    def source_url(self):
        return (self.get("reference") or {}).get("source_url")

    @property
    def captured_at(self):
        return (self.get("metadata") or {}).get("captured_at")

    @property
    def source_page_id(self):
        return (self.get("metadata") or {}).get("source_page_id")

    # gap-aware navigation: None when the neighbor is absent (beginning /
    # end of corpus) — the full reference object is in
    # "next_page_reference" / "previous_page_reference" (may carry
    # in_missing_range, next/prev_available_item_index, ...).
    @property
    def next_item_index(self):
        ref = self.get("next_page_reference") or {}
        return ref.get("item_index") if ref.get("exists") else None

    @property
    def previous_item_index(self):
        ref = self.get("previous_page_reference") or {}
        return ref.get("item_index") if ref.get("exists") else None


class TopicDetail(dict):
    """The ``/topics/{topic_id}`` payload as a dict, with convenience
    properties."""

    @property
    def topic_id(self):
        return self.get("topic_id")

    @property
    def display_text(self):
        return self.get("display_text")

    @property
    def normalized_text(self):
        return self.get("normalized_text")

    @property
    def page_count(self):
        return self.get("page_count")

    @property
    def volume_count(self):
        return self.get("volume_count")

    @property
    def occurrences_total(self):
        return self.get("occurrences_total")

    @property
    def occurrences(self):
        return self.get("occurrences") or []

    @property
    def sample_pages(self):
        return self.get("sample_pages") or []

    @property
    def first_item_index(self):
        return self.get("first_item_index")

    @property
    def first_page_id(self):
        return self.get("first_page_id")

    @property
    def parent_topic(self):
        return self.get("parent_topic")


# ---------------------------------------------------------------------------
# the client
# ---------------------------------------------------------------------------

class TasnimClient:
    """Read-only client for the Tasnim Web V1 API.

    Args:
        base_url: server root, e.g. ``"https://tasnim.ai.ismc.ir"`` or
            ``"http://127.0.0.1:5071"``. A trailing ``/api/v1/tasnim``
            (with or without slash) is allowed and not doubled.
        timeout: per-request socket timeout in seconds.
        rate_limit_backoff: on 429, sleep ``Retry-After`` (capped) and
            retry, up to ``max_retries`` times; when False, the
            ``TasnimAPIError`` (code ``RATE_LIMITED``) is raised
            immediately.
        max_retries: how many extra attempts after the first on 429.
        max_backoff_s: cap for a single sleep (the server's
            ``Retry-After`` can be up to 60 s).
        etag_cache: keep an in-memory ``If-None-Match`` cache; on 304 the
            previously returned response is reused (``from_cache=True``).
            Search results are ``no-store`` and never hit 304.
        clock / sleep: injectable for tests (default ``time.time`` /
            ``time.sleep``).
        user_agent: sent as ``User-Agent``.
    """

    def __init__(self, base_url, timeout=DEFAULT_TIMEOUT,
                 rate_limit_backoff=True, max_retries=3,
                 max_backoff_s=65, etag_cache=True,
                 clock=None, sleep=None, user_agent=DEFAULT_USER_AGENT):
        if not base_url:
            raise ValueError("base_url is required")
        root = base_url.rstrip("/")
        if root.endswith(API_PREFIX):
            root = root[: -len(API_PREFIX)].rstrip("/")
        self.root = root
        self.timeout = timeout
        self.rate_limit_backoff = rate_limit_backoff
        self.max_retries = max_retries
        self.max_backoff_s = max_backoff_s
        self.etag_cache = etag_cache
        self._etag_store = {}
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        self._user_agent = user_agent

    # -- public API: the 12 endpoints --------------------------------------

    def get_catalog(self):
        """GET /catalog — work/edition identity + live counts + coverage.

        ETag-cached (strong), ``Cache-Control: public, max-age=60``."""
        r = self._request("GET", "/catalog", etag=True)
        return r

    def list_volumes(self, limit=50, offset=None, page_token=None,
                     sort="volume_no"):
        """GET /volumes — paginated volume list.

        ``sort``: ``"volume_no"`` (default) or ``"page_count"``.
        Use :meth:`iter_volumes` to walk all pages."""
        params = {"limit": limit, "sort": sort}
        self._add_paging(params, offset, page_token)
        r = self._request("GET", "/volumes", params=params, etag=True)
        return r

    def iter_volumes(self, limit=50, sort="volume_no"):
        """Yield volume dicts across all /volumes pages (token chain)."""
        token = None
        while True:
            r = self.list_volumes(limit=limit, sort=sort, page_token=token)
            for item in r.data.get("items") or []:
                yield item
            token = r.next_page_token
            if not token:
                return

    def get_volume(self, volume_id):
        """GET /volumes/{volume_id} — full volume record. 404
        ``VOLUME_NOT_FOUND`` if the id is not in the read model."""
        r = self._request("GET", "/volumes/" + self._quote(volume_id),
                          etag=True)
        return r

    def get_surahs(self):
        """GET /surahs — always 503 ``SURAH_INDEX_NOT_SUPPORTED`` in V1
        (honest unavailability; see the error ``details.evidence``)."""
        return self._request("GET", "/surahs", etag=False)

    def get_surah(self, surah_id):
        """GET /surahs/{surah_id} — always 503 in V1 (as above)."""
        return self._request("GET", "/surahs/" + self._quote(surah_id),
                             etag=False)

    def list_topics(self, limit=50, offset=None, page_token=None, q=None,
                    min_pages=None, sort="page_count"):
        """GET /topics — paginated topic list.

        ``q`` filters by normalized-text *prefix*; ``min_pages`` filters
        ``page_count >= n``; ``sort``: ``"page_count"`` (default) or
        ``"name"``. Use :meth:`iter_topics` to walk all pages."""
        params = {"limit": limit, "sort": sort}
        if q is not None:
            params["q"] = q
        if min_pages is not None:
            params["min_pages"] = min_pages
        self._add_paging(params, offset, page_token)
        r = self._request("GET", "/topics", params=params, etag=True)
        return r

    def iter_topics(self, limit=50, q=None, min_pages=None,
                    sort="page_count"):
        """Yield topic dicts across all /topics pages (token chain)."""
        token = None
        while True:
            r = self.list_topics(limit=limit, q=q, min_pages=min_pages,
                                 sort=sort, page_token=token)
            for item in r.data.get("items") or []:
                yield item
            token = r.next_page_token
            if not token:
                return

    def get_topic(self, topic_id):
        """GET /topics/{topic_id} → :class:`TopicDetail` (occurrences are
        paginated server-side; the list is in ``occurrences`` and the
        total in ``occurrences_total``). 404 ``TOPIC_NOT_FOUND``."""
        r = self._request("GET", "/topics/" + self._quote(topic_id),
                          etag=True)
        return TopicDetail(r.data)

    def get_page(self, item_index, dup_rank=0):
        """GET /pages/{item_index} → :class:`Page` (the heart of the
        contract: gap-aware next/prev references, quality, duplicates,
        provenance metadata, ``rag_status``).

        404 ``PAGE_NOT_FOUND`` carries ``details.in_missing_range`` and a
        ``suggestion`` of the nearest available pages."""
        params = {}
        if dup_rank:
            params["dup_rank"] = dup_rank
        r = self._request("GET", "/pages/%d" % int(item_index),
                          params=params or None, etag=True)
        return Page(r.data)

    def iter_pages(self, item_index_min, item_index_max, dup_rank=0,
                   on_missing="skip"):
        """Yield :class:`Page` for each existing ``item_index`` in
        ``[min, max]``.

        Missing indexes (gaps) raise nothing by default (``skip``) — the
        corpus has real gaps and gap-awareness is the point; with
        ``on_missing="raise"`` a ``PAGE_NOT_FOUND`` propagates. Note:
        each page is one read-class request (120/min per IP); for big
        ranges consider the corpus dumps instead of the live API."""
        for ii in range(int(item_index_min), int(item_index_max) + 1):
            try:
                yield self.get_page(ii, dup_rank=dup_rank)
            except TasnimAPIError as e:
                if e.code == "PAGE_NOT_FOUND" and on_missing == "skip":
                    continue
                raise

    def get_page_neighbors(self, item_index):
        """GET /pages/{item_index}/neighbors — gap-aware prev/next
        reference objects + ``missing_nearby`` ranges."""
        r = self._request("GET", "/pages/%d/neighbors" % int(item_index),
                          etag=True)
        return r

    def search(self, q, volume_id=None, sort="relevance", limit=20,
               offset=None, page_token=None):
        """GET /search — full-text (Persian-stemmed) search.

        ``q`` must be 2..64 chars; 3+ tokens switch to *estimated*
        results (``total == -1`` and ``data.estimated == True``).
        Zero hits (exact mode) return ``suggestions`` (top topics).
        Responses are ``no-store`` (weak ETag) — not etag-cached.
        Search-class rate limit: 30/min."""
        params = {"q": q, "limit": limit, "sort": sort}
        if volume_id is not None:
            params["volume_id"] = volume_id
        self._add_paging(params, offset, page_token)
        return self._request("GET", "/search", params=params, etag=False)

    def get_statistics(self):
        """GET /statistics — live GROUP BY counters with written
        definitions (pages_by_class, quality_status, item_index
        incl. missing ranges, text_length percentiles, topics, surah)."""
        return self._request("GET", "/statistics", etag=True)

    def get_health(self):
        """GET /health — readmodel identity + db quick check + uptime.
        Exempt from rate limiting (safe for probes)."""
        return self._request("GET", "/health", etag=False)

    # -- plumbing ------------------------------------------------------------

    @staticmethod
    def _quote(value):
        return urllib.parse.quote(str(value), safe="")

    @staticmethod
    def _add_paging(params, offset, page_token):
        if page_token is not None:
            params["page_token"] = page_token
        elif offset is not None:
            params["offset"] = offset

    def _url(self, path, params):
        url = self.root + API_PREFIX + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def _request(self, method, path, params=None, etag=False):
        url = self._url(path, params)
        while True:
            headers = {"User-Agent": self._user_agent,
                       "Accept": "application/json"}
            if etag and self.etag_cache and url in self._etag_store:
                cached, cached_etag = self._etag_store[url]
                headers["If-None-Match"] = cached_etag
            status, hdrs, body = self._http(method, url, headers)
            data = self._parse(body, url)
            if status == 304 and etag and self.etag_cache:
                cached, _ = self._etag_store.get(url, (None, None))
                if cached is not None:
                    cached.from_cache = True
                    return cached
            if status == 200 and isinstance(data, TasnimResponse):
                # Surface the response headers on the response object
                # (TasnimResponse.etag / .cache_control).
                data.etag = hdrs.get("ETag")
                data.cache_control = hdrs.get("Cache-Control")
                if etag and self.etag_cache and data.etag:
                    self._etag_store[url] = (data, data.etag)
            return data

    def _http(self, method, url, headers):
        """One GET (with 429 backoff). Returns (status, headers-dict,
        body-bytes). HTTP errors become TasnimAPIError; transport
        failures (DNS, refused, timeout) become TasnimClientError.
        429 is retried (with capped Retry-After sleep) while
        ``rate_limit_backoff`` and attempts remain; otherwise a
        TasnimAPIError with code RATE_LIMITED is raised."""
        attempt = 0
        while True:
            req = urllib.request.Request(url, method=method,
                                         headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return (r.status, dict(r.headers.items()),
                            r.read())
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    # urllib raises on non-2xx; 304 Not Modified is a
                    # successful cache hit, not an error.
                    try:
                        body = e.read()
                    except Exception:
                        body = b""
                    return (304, dict(e.headers.items()
                                      if e.headers else {}), body)
                if (e.code == 429 and self.rate_limit_backoff
                        and attempt < self.max_retries):
                    retry_after = e.headers.get("Retry-After") if e.headers \
                        else None
                    try:
                        wait = float(retry_after) if retry_after else None
                    except ValueError:
                        wait = None
                    if wait is None:
                        wait = min(self.max_backoff_s,
                                   1.5 ** attempt)
                    wait = max(1.0, min(wait, self.max_backoff_s))
                    self._sleep(wait)
                    attempt += 1
                    continue
                # drain the body (urllib otherwise leaves it unread)
                try:
                    body = e.read()
                except Exception:
                    body = b""
                raise self._api_error(e, body, url) from None
            except (urllib.error.URLError, ConnectionError,
                    socket.timeout, OSError) as e:
                # DNS failure, connection refused, socket timeout, ...
                raise TasnimClientError(
                    "transport error on %s: %s" % (url, e)) from e

    @staticmethod
    def _parse(body, url):
        if not body:
            return None
        try:
            obj = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise TasnimClientError(
                "non-JSON response from %s: %s" % (url, e)) from None
        if isinstance(obj, dict) and "data" in obj:
            data = TasnimResponse(
                obj.get("data"), obj.get("meta"),
                etag=None)  # etag set by caller via headers below
            return data
        return obj  # error envelopes handled by _raise_for_error

    def _api_error(self, e, body, url):
        try:
            obj = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            obj = None
        retry_after = None
        try:
            ra = e.headers.get("Retry-After") if e.headers else None
            retry_after = int(ra) if ra and str(ra).isdigit() else None
        except (ValueError, TypeError):
            retry_after = None
        if isinstance(obj, dict) and "code" in obj and "status" in obj:
            return TasnimAPIError(
                status=obj.get("status", e.code),
                code=obj.get("code"),
                title=obj.get("title"),
                message=obj.get("message"),
                details=obj.get("details"),
                request_id=obj.get("request_id"),
                type_=obj.get("type"),
                retry_after=retry_after,
                body=obj,
            )
        return TasnimClientError(
            "HTTP %d from %s: %s" % (e.code, url,
                                     body[:200].decode("utf-8", "replace")))

    # -- misc ---------------------------------------------------------------

    def clear_etag_cache(self):
        self._etag_store.clear()

    def __repr__(self):
        return "TasnimClient(base_url=%r)" % self.root

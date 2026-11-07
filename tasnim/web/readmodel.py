# -*- coding: utf-8 -*-
"""Tasnim Web V1 — read model builder (PCM-20.6.4, Track B).

Reads a corpus build directory (READ-ONLY) and produces a queryable
SQLite read model.

Output layout (per corpus version, e.g. tasnim/data/readmodel/v0003/):
  tasnim_readmodel.db   main read model (SQLite + FTS5)
  build_meta.db         build metadata — SEPARATE file (per spec note
                        «build_meta.db داخل readmodel dir») so it can
                        store the sha256 of the main db
  build.sha256          sidecar hashes
  build-report.json     timing / sizes / shas / invariants
  covers/<volume_id>.svg deterministic cover plates (design system §7.8)

Documented deviations from PCM-20.6.4-ARCHITECTURE.md:
* pages_fts is a STANDALONE FTS5 table. The spec's external-content DDL
  (content='pages') would map its 3rd column ``tokens`` onto pages' 3rd
  column ``dup_rank`` — a column-mapping bug. Tokens are pre-computed
  (tokenize_fa/1.0) and stored both in ``pages.text_tokens`` and in the
  FTS table itself.
* FTS index token range is ``[\\u0600-\\u06FF\\u0750-\\u077F]`` not the spec's
  ``[\\u0621-\\u064A]`` — the spec range would drop Persian-specific letters
  (گ پ چ ژ …). Documented errata per §4.6.
* ``page_content_hash_note``: ``content_hash`` in pages.jsonl is a
  crawler-side hash (not reproducible from page text — verified by
  probe); it is stored verbatim under the spec's column name
  ``content_sha256``.
* ``/statistics`` quality_status = live GROUP BY of pages.status; the
  manifest's ``quality_flag_counts`` are FLAG counts (a page can carry
  several flags, e.g. short+dup) and are used for build-time validation,
  not as the status definition.

Invariants (spec §4.3), all test-backed:
1. source read-only — corpus files opened read-only only;
2. deterministic — ordered/streamed inserts, fixed pragmas, no
   timestamps in the DB, final VACUUM (test: two builds = same SHA);
3. version directory — output under the caller-given --out dir;
4. bounded memory — line-by-line streaming, commit every 5,000 rows;
5. HP-1 — ``hidden-context-records.jsonl`` / ``context-records.jsonl``
   are NEVER opened (hard guard); only pages.jsonl, heading-records.jsonl,
   corpus.json, manifest.json are read;
6. validation vs manifest — mismatch = build fail.
"""
import hashlib
import json
import os
import re
import sqlite3
import time
from collections import Counter

SCHEMA_VERSION = "tasnim-readmodel/1.0"
TOPIC_NORM_VERSION = "tasnim-topic-norm/1.0"
TOKENIZER_VERSION = "tokenize_fa/1.0"
RAG_STATUS = "not_connected"
COMMIT_EVERY = 5000

ALLOWED_SOURCE_FILES = ("pages.jsonl", "heading-records.jsonl",
                        "corpus.json", "manifest.json")
FORBIDDEN_SOURCE_FILES = ("hidden-context-records.jsonl",
                          "context-records.jsonl")

# --------------------------------------------------------------------------
# text normalization (topic identity + FTS) — shared with the API layer
# --------------------------------------------------------------------------

_DIGIT_MAP = {str(i): str(i) for i in range(10)}
for _base in (0x06F0, 0x0660):  # ۰-۹ (extended) and ٠-٩ (arabic-indic)
    for _i in range(10):
        _DIGIT_MAP[chr(_base + _i)] = chr(ord("0") + _i)

# Spec §4.5 step (5): hamza unification. ٔ/ٴ (modifier hamzas) are DROPPED;
# explicit ٲ→ا, ٵ→ئ, ە→ه, ۍ→ی.
HAMZA_MAP = {
    "\u0654": "",   # ٔ ARABIC MODIFIER LETTER HAMZA ABOVE
    "\u0674": "",   # ٴ ARABIC LETTER HAMZA (used as modifier, e.g. گزیدهٴ)
    "\u0672": "\u0627",  # ٲ → ا
    "\u0675": "\u06CC",  # ٵ → ئ
    "\u06D5": "\u0647",  # ە → ه
    "\u06CD": "\u06CC",  # ۍ → ی
}

# Leading number: "(12)" / "[12]" / "12)" "12]" "12." "12-" "12:"  (spec §4.5
# step 4, combined with the fact-check NUM_PREFIX_RE which also allowed
# bracketed form). Applied twice, exactly as the verified fact-check code.
NUM_PREFIX_RE = re.compile(r"^(?:\(\d{1,3}\)|\[\d{1,3}\]|\d{1,3}[\)\]\.\-\:])\s*")


def normalize_topic(text):
    """tasnim-topic-norm/1.0 (spec §4.5):

    (1) strip; (2) digits ۰-۹/٠-٩ → ASCII; (3) collapse whitespace;
    (4) strip leading number (applied twice, as in the verified
    fact-check); (5) hamza unification; (6) strip ' .:ـ-' from the end.
    """
    t = text.strip()
    t = "".join(_DIGIT_MAP.get(ch, ch) for ch in t)
    t = re.sub(r"\s+", " ", t)
    t = NUM_PREFIX_RE.sub("", t)
    t = NUM_PREFIX_RE.sub("", t)  # repeat once (fact-check behaviour)
    t = "".join(HAMZA_MAP.get(ch, ch) for ch in t)
    t = t.strip(" .:\u0640-")
    return t


def topic_id_of(normalized_text):
    """Stable identity: 't-' + sha1(normalized)[:12]."""
    return "t-" + hashlib.sha1(normalized_text.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# FTS tokenization (tokenize_fa/1.0) — spec §4.6
# --------------------------------------------------------------------------

ZWNJ = "\u200C"
_TOKEN_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]+|[0-9]+|[A-Za-z]+")


def _strip_diacritics(ch):
    o = ord(ch)
    if 0x064B <= o <= 0x065F:      # Arabic diacritics (tashkeel)
        return None
    if ch == "\u0670":             # superscript alef
        return None
    if 0x08D3 <= o <= 0x08FF:      # Arabic extended diacritics
        return None
    return ch


def tokenize_fa(text):
    """tokenize_fa/1.0: digits→ASCII, diacritics DELETED (Arabic text in
    this corpus is fully voweled — deletion, not space), ZWNJ→space,
    punctuation dropped; tokens = runs of [Arabic block + extended
    Arabic], digits, latin. Deterministic, no dependency.

    Documented limitations (§4.6): no Persian stemming; prefix matching
    covers suffix morphology; ZWNJ-split compounds search with a space.
    """
    if not text:
        return []
    t = "".join(_DIGIT_MAP.get(ch, ch) for ch in text)
    t = t.replace(ZWNJ, " ")
    chars = []
    for ch in t:
        c = _strip_diacritics(ch)
        if c is not None:
            chars.append(c)
    return _TOKEN_RE.findall("".join(chars))


def build_fts_match(tokens):
    """Prefix AND query: each token quoted (FTS-safe) + '*' prefix."""
    return " AND ".join('"%s"*' % t for t in tokens)


def make_snippet(text, token, before=60, after=120):
    """Snippet from the ORIGINAL text (readability), with diacritic/ZWNJ/
    digit-insensitive matching. Returns a list of (segment, marked)
    tuples; exactly one marked segment on hit, none on miss (fallback =
    first 220 chars, no mark)."""
    if not text:
        return []
    norm_chars = []
    pos_map = []
    for i, ch in enumerate(text):
        c = _strip_diacritics(ch)
        if c is None:
            continue
        if ch == ZWNJ:
            c = " "
        c = _DIGIT_MAP.get(c, c)
        norm_chars.append(c)
        pos_map.append(i)
    norm = "".join(norm_chars).lower()
    tl = token.lower()
    m = norm.find(tl)
    if m < 0 or not pos_map:
        return [(text[:220], False)]
    orig_start = pos_map[m]
    orig_end = pos_map[m + len(tl) - 1] + 1
    ws = max(0, orig_start - before)
    we = min(len(text), orig_end + after)
    segs = []
    if ws > 0:
        segs.append(("\u2026", False))
    if orig_start > ws:
        segs.append((text[ws:orig_start], False))
    segs.append((text[orig_start:orig_end], True))
    if we > orig_end:
        segs.append((text[orig_end:we], False))
    if we < len(text):
        segs.append(("\u2026", False))
    return segs


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE works(
  work_id TEXT PRIMARY KEY,
  work_name TEXT NOT NULL
);
CREATE TABLE editions(
  edition_id TEXT PRIMARY KEY,
  work_id TEXT NOT NULL REFERENCES works(work_id),
  edition_name TEXT NOT NULL,
  source_version TEXT,
  exported_at TEXT
);
CREATE TABLE volumes(
  volume_id TEXT PRIMARY KEY,
  edition_id TEXT NOT NULL REFERENCES editions(edition_id),
  volume_no INTEGER,
  volume_title TEXT,
  volume_strategy TEXT,
  page_count INTEGER NOT NULL,
  item_index_min INTEGER NOT NULL,
  item_index_max INTEGER NOT NULL,
  ambiguity_flag INTEGER NOT NULL DEFAULT 0,
  overlap_note TEXT
);
CREATE TABLE pages(
  page_id TEXT PRIMARY KEY,
  item_index INTEGER NOT NULL,
  dup_rank INTEGER NOT NULL DEFAULT 0,
  volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
  barg INTEGER,
  section TEXT,
  content_sha256 TEXT,
  char_count INTEGER NOT NULL,
  record_class TEXT,
  status TEXT NOT NULL,
  flag_short INTEGER NOT NULL DEFAULT 0,
  flag_empty INTEGER NOT NULL DEFAULT 0,
  flag_truncated_2000 INTEGER NOT NULL DEFAULT 0,
  dup_of TEXT,
  seq_in_volume INTEGER NOT NULL,
  seq_global INTEGER NOT NULL,
  heading_record_id TEXT,
  context_record_id TEXT,
  next_page_id TEXT,
  next_item_index INTEGER,
  captured_at TEXT,
  source_page_id INTEGER,
  url TEXT,
  text TEXT NOT NULL,
  text_normalized TEXT,
  text_tokens TEXT
);
CREATE INDEX idx_pages_ii ON pages(item_index, dup_rank);
CREATE INDEX idx_pages_vol ON pages(volume_id, item_index);
CREATE TABLE headings(
  record_id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  item_index INTEGER NOT NULL,
  volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
  heading_text TEXT NOT NULL,
  heading_hash TEXT,
  normalized_text TEXT NOT NULL,
  topic_id TEXT NOT NULL,
  parent_heading_page_id TEXT,
  next_page_id TEXT,
  children_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_headings_topic ON headings(topic_id);
CREATE INDEX idx_headings_vol ON headings(volume_id, item_index);
CREATE INDEX idx_headings_page ON headings(page_id);
CREATE TABLE topics(
  topic_id TEXT PRIMARY KEY,
  normalized_text TEXT NOT NULL UNIQUE,
  display_text TEXT NOT NULL,
  page_count INTEGER NOT NULL,
  volume_count INTEGER NOT NULL,
  first_page_id TEXT NOT NULL,
  first_item_index INTEGER NOT NULL
);
CREATE TABLE surahs(
  surah_id TEXT PRIMARY KEY,
  canonical_name TEXT,
  confidence REAL,
  page_count INTEGER
);
CREATE VIRTUAL TABLE pages_fts USING fts5(
  page_id UNINDEXED, item_index UNINDEXED, tokens, tokenize='unicode61'
);
CREATE TABLE coverage(
  scope TEXT NOT NULL,
  missing_from INTEGER NOT NULL,
  missing_to INTEGER NOT NULL,
  missing_count INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'backfill_pending',
  note TEXT
);
CREATE INDEX idx_coverage_scope ON coverage(scope);
"""

PAGE_COLUMNS = [
    "page_id", "item_index", "dup_rank", "volume_id", "barg", "section",
    "content_sha256", "char_count", "record_class", "status", "flag_short",
    "flag_empty", "flag_truncated_2000", "dup_of", "seq_in_volume",
    "seq_global", "heading_record_id", "context_record_id", "next_page_id",
    "next_item_index", "captured_at", "source_page_id", "url", "text",
    "text_normalized", "text_tokens",
]


class BuildError(Exception):
    pass


def _expect(cond, msg):
    if not cond:
        raise BuildError(msg)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _runs_of_missing(present, lo, hi):
    """Runs of integers in [lo, hi] absent from `present` (a set)."""
    runs = []
    start = None
    for x in range(lo, hi + 1):
        if x in present:
            if start is not None:
                runs.append((start, x - 1))
                start = None
        elif start is None:
            start = x
    if start is not None:
        runs.append((start, hi))
    return runs


def _runs_of(xs):
    """Consecutive runs of a sorted list of ints, as [[a,b], ...]."""
    rs = []
    st = pv = xs[0]
    for x in xs[1:]:
        if x == pv + 1:
            pv = x
        else:
            rs.append([st, pv])
            st = pv = x
    rs.append([st, pv])
    return rs


def _vol_part_of_page_id(page_id):
    i = page_id.rfind("__p")
    return page_id[:i] if i > 0 else page_id


def _gaps_reason(mdata):
    g = ((mdata or {}).get("gaps") or {}).get("missing_item_index") or {}
    return str(g.get("reason") or "backfill pending (Track A)")


def _dig(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


# --------------------------------------------------------------------------
# builder
# --------------------------------------------------------------------------

class ReadModelBuilder:
    def __init__(self, corpus_dir, out_dir):
        self.corpus_dir = os.path.abspath(corpus_dir)
        self.out_dir = os.path.abspath(out_dir)
        self.opened_files = []

    # -- HP-1 layer 1: hard guard on which files may be opened -------------
    def _open(self, name):
        if name in FORBIDDEN_SOURCE_FILES:
            raise BuildError(
                "HP-1 violation: builder must never open %r" % name)
        self.opened_files.append(name)
        return open(os.path.join(self.corpus_dir, name), "r",
                    encoding="utf-8")

    # -- build --------------------------------------------------------------
    def build(self):
        t0 = time.time()
        _expect(os.path.isdir(self.corpus_dir),
                "corpus dir not found: %s" % self.corpus_dir)
        os.makedirs(os.path.join(self.out_dir, "covers"), exist_ok=True)

        corpus = json.load(self._open("corpus.json"))
        manifest = json.load(self._open("manifest.json"))
        mdata = manifest.get("data", {})
        mfiles = mdata.get("files", {})
        mstats = mdata.get("stats", {})
        mtrunc = (corpus.get("semantic") or {}).get("truncation") or {}

        # source integrity: verify every manifest-listed file we open
        source_files = []
        for name in ALLOWED_SOURCE_FILES:
            path = os.path.join(self.corpus_dir, name)
            sha = sha256_file(path)
            expected = (mfiles.get(name) or {}).get("sha256")
            if expected is not None:
                _expect(expected == sha,
                        "source %s sha256 mismatch (manifest vs disk)"
                        % name)
            source_files.append({
                "name": name, "sha256": sha,
                "size_bytes": os.path.getsize(path),
                "verified": expected is not None and expected == sha,
            })

        db_path = os.path.join(self.out_dir, "tasnim_readmodel.db")
        for stale in (db_path, db_path + "-wal", db_path + "-shm",
                      os.path.join(self.out_dir, "build_meta.db")):
            if os.path.exists(stale):
                os.remove(stale)

        conn = self._connect(db_path)
        try:
            self._pages_pass(conn)
            self._headings_pass(conn, corpus)
            self._topics_pass(conn)
            self._meta_tables_pass(conn, corpus, mdata)
            self._dup_of_pass(conn)
            self._validate(conn, corpus, mdata, mstats, mtrunc)
            conn.commit()
            conn.execute("PRAGMA optimize")
            conn.execute("VACUUM")
            conn.commit()
        finally:
            conn.close()

        db_sha = sha256_file(db_path)
        self._write_build_meta(db_sha, source_files, corpus, mdata)
        self._write_sidecars(db_sha)
        self._write_covers(corpus)
        return self._report(corpus, mdata, db_sha, t0)

    def _connect(self, db_path):
        conn = sqlite3.connect(db_path)
        # fixed pragmas → deterministic file for identical input
        conn.execute("PRAGMA page_size=4096")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA cache_size=-131072")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        return conn

    # -- pass 1: pages.jsonl (streaming) ------------------------------------
    def _pages_pass(self, conn):
        ins = conn.cursor()
        ins_sql = ("INSERT INTO pages(%s) VALUES(%s)" % (
            ",".join(PAGE_COLUMNS), ",".join("?" * len(PAGE_COLUMNS))))
        fts_ins = conn.cursor()
        fts_sql = "INSERT INTO pages_fts(page_id, item_index, tokens) VALUES(?,?,?)"
        n = 0
        self.ii_rows = {}          # ii -> [(dup_rank, page_id, volume_id)]
        self.vol_ii = {}           # volume_id -> set(ii)
        self.vol_pages = {}        # volume_id -> [count, min_ii, max_ii]
        self.class_counts = Counter()
        self.status_counts = Counter()
        self.flag_counts = Counter()
        self.truncated_ids = set()
        self.page_ids = set()
        self.min_ii = None
        self.max_ii = None
        seq_fb = 0

        with self._open("pages.jsonl") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                page_id = rec["page_id"]
                _expect(page_id not in self.page_ids,
                        "duplicate page_id in pages.jsonl: %s" % page_id)
                self.page_ids.add(page_id)

                sem = rec.get("semantic") or {}
                order = sem.get("order") or {}
                qc = rec.get("quality_status") or {}
                hc = sem.get("hidden_context") or {}
                volblk = rec.get("volume") or {}
                md = rec.get("metadata") or {}

                ii = int(rec["item_index"])
                dup_rank = int(order.get("dup_rank", 0) or 0)
                vol_id = rec.get("volume_id") or volblk.get("volume_id")
                _expect(vol_id is not None,
                        "page without volume_id: %s" % page_id)
                text = rec.get("text") or ""
                text_norm = rec.get("text_normalized") or text
                flags = qc.get("flags") or []
                status = qc.get("status") or "ok"
                seq_in_volume = order.get("seq_in_volume")
                if seq_in_volume is None:
                    seq_in_volume = rec.get("position", n)
                seq_global = order.get("seq_global")
                if seq_global is None:
                    seq_global = seq_fb
                    seq_fb += 1

                # R1 stop-condition: next_page_id must never cross volumes
                npid = rec.get("next_page_id")
                if npid:
                    _expect(_vol_part_of_page_id(npid) ==
                            _vol_part_of_page_id(page_id),
                            "R1: cross-volume next_page_id at %s → %s "
                            "(stop: contract review required)"
                            % (page_id, npid))

                trunc = sem.get("truncation") or {}
                tokens = " ".join(tokenize_fa(text_norm))
                row = (
                    page_id, ii, dup_rank, vol_id, rec.get("barg"),
                    md.get("section"), rec.get("content_hash"), len(text),
                    sem.get("record_class"), status,
                    1 if "short" in flags else 0,
                    1 if "empty" in flags else 0,
                    1 if "truncated_at_2000" in flags else 0,
                    None,  # dup_of — fixed up later
                    int(seq_in_volume), int(seq_global),
                    hc.get("heading_record_id"),
                    hc.get("context_record_id"),
                    npid,
                    rec.get("next_item_index"),
                    rec.get("captured_at"),
                    rec.get("source_page_id"),
                    rec.get("url"),
                    text, text_norm, tokens,
                )
                ins.execute(ins_sql, row)
                fts_ins.execute(fts_sql, (page_id, ii, tokens))

                if "truncated_at_2000" in flags:
                    _expect(bool(trunc.get("truncated_at_source")),
                            "flag truncated_at_2000 without "
                            "truncated_at_source: %s" % page_id)
                    self.truncated_ids.add(page_id)
                self.class_counts[sem.get("record_class") or "UNKNOWN"] += 1
                self.status_counts[status] += 1
                for fl in flags:
                    self.flag_counts[fl] += 1
                if not flags:
                    # corpus-factory convention: "ok" = page with no flags
                    # (see corpus/tasnim/reconcile.py::_flag_counts)
                    self.flag_counts["ok"] += 1
                self.ii_rows.setdefault(ii, []).append(
                    (dup_rank, page_id, vol_id))
                self.vol_ii.setdefault(vol_id, set()).add(ii)
                vp = self.vol_pages.setdefault(vol_id, [0, ii, ii])
                vp[0] += 1
                vp[1] = min(vp[1], ii)
                vp[2] = max(vp[2], ii)
                if self.min_ii is None or ii < self.min_ii:
                    self.min_ii = ii
                if self.max_ii is None or ii > self.max_ii:
                    self.max_ii = ii
                n += 1
                if n % COMMIT_EVERY == 0:
                    conn.commit()
        self.page_count = n

    # -- pass 2: heading-records.jsonl (streaming) --------------------------
    def _headings_pass(self, conn, corpus):
        expected = _dig(corpus, "semantic", "hidden_context",
                        "heading_records", "count")
        ins = conn.cursor()
        ins_sql = (
            "INSERT INTO headings(record_id, page_id, item_index, volume_id,"
            " heading_text, heading_hash, normalized_text, topic_id,"
            " parent_heading_page_id, next_page_id, children_count)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)")
        n = 0
        orphans = 0
        self.topics_agg = {}
        with self._open("heading-records.jsonl") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                page_id = rec["page_id"]
                _expect(page_id in self.page_ids,
                        "heading references unknown page: %s" % page_id)
                parent = rec.get("parent_heading_page_id")
                if parent and parent not in self.page_ids:
                    orphans += 1
                text = rec.get("heading_text") or ""
                norm = normalize_topic(text)
                tid = topic_id_of(norm)
                vol_id = rec.get("volume_id")
                ii = int(rec["item_index"])
                ins.execute(ins_sql, (
                    rec["record_id"], page_id, ii, vol_id, text,
                    rec.get("heading_hash"), norm, tid,
                    rec.get("parent_heading_page_id"), rec.get("next_page_id"),
                    len(rec.get("children_page_ids") or []),
                ))
                agg = self.topics_agg.setdefault(norm, {
                    "forms": Counter(), "pages": set(), "vols": set(),
                    "first": (ii, page_id),
                })
                agg["forms"][text] += 1
                agg["pages"].add(page_id)
                if vol_id is not None:
                    agg["vols"].add(vol_id)
                key = (ii, page_id)
                if key < agg["first"]:
                    agg["first"] = key
                n += 1
                if n % COMMIT_EVERY == 0:
                    conn.commit()
        _expect(orphans == 0,
                "%d headings with unresolvable parent (orphan>0)" % orphans)
        if expected is not None:
            _expect(n == int(expected),
                    "heading count %d != corpus.json heading_records.count %s"
                    % (n, expected))
        self.heading_count = n

    # -- pass 3: topics -------------------------------------------------------
    def _topics_pass(self, conn):
        cur = conn.cursor()
        for norm in sorted(self.topics_agg):
            agg = self.topics_agg[norm]
            forms = agg["forms"]
            # most frequent raw form; tie → lexicographically smallest
            display = min(forms.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            first_ii, first_page = agg["first"]
            cur.execute(
                "INSERT INTO topics(topic_id, normalized_text, display_text,"
                " page_count, volume_count, first_page_id, first_item_index)"
                " VALUES(?,?,?,?,?,?,?)",
                (topic_id_of(norm), norm, display, len(agg["pages"]),
                 len(agg["vols"]), first_page, first_ii))
        self.topic_count = len(self.topics_agg)

    # -- pass 4: works / editions / volumes / coverage ------------------------
    def _meta_tables_pass(self, conn, corpus, mdata):
        cur = conn.cursor()
        work = corpus.get("work") or {}
        edition = corpus.get("edition") or {}
        cur.execute("INSERT INTO works(work_id, work_name) VALUES(?,?)",
                    (work.get("work_id"), work.get("work_name")))
        cur.execute(
            "INSERT INTO editions(edition_id, work_id, edition_name,"
            " source_version, exported_at) VALUES(?,?,?,?,?)",
            (edition.get("edition_id"), work.get("work_id"),
             edition.get("edition_name"), edition.get("source_version"),
             edition.get("exported_at")))
        self.work_id = work.get("work_id")
        self.edition_id = edition.get("edition_id")

        # overlap detection (ambiguity) across volumes, by shared item_index
        vol_ids = sorted(self.vol_ii)
        overlaps = {v: [] for v in vol_ids}
        for i, a in enumerate(vol_ids):
            for b in vol_ids[i + 1:]:
                common = sorted(self.vol_ii[a] & self.vol_ii[b])
                if not common:
                    continue
                ov = {"volume_id": b, "ranges": _runs_of(common),
                      "item_index_count": len(common)}
                overlaps[a].append(ov)
                overlaps[b].append(dict(ov, volume_id=a))

        for v in corpus.get("volumes") or []:
            vid = v["volume_id"]
            _expect(vid in self.vol_pages,
                    "corpus.json volume without pages: %s" % vid)
            count, vmin, vmax = self.vol_pages[vid]
            _expect(count == int(v.get("page_count", -1)),
                    "volume %s page_count %d != corpus.json %s"
                    % (vid, count, v.get("page_count")))
            span = v.get("item_index_span") or [vmin, vmax]
            _expect([vmin, vmax] == [int(span[0]), int(span[1])],
                    "volume %s span %s != corpus.json %s"
                    % (vid, [vmin, vmax], span))
            ovl = overlaps.get(vid, [])
            cur.execute(
                "INSERT INTO volumes(volume_id, edition_id, volume_no,"
                " volume_title, volume_strategy, page_count, item_index_min,"
                " item_index_max, ambiguity_flag, overlap_note)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (vid, self.edition_id, v.get("volume_no"),
                 v.get("volume_title"), v.get("volume_strategy"), count,
                 vmin, vmax, 1 if ovl else 0,
                 json.dumps(ovl, ensure_ascii=False) if ovl else None))
        self.volume_count = len(vol_ids)

        # coverage: global — one row per missing run
        present = set(self.ii_rows)
        runs = _runs_of_missing(present, self.min_ii, self.max_ii)
        missing_total = sum(b - a + 1 for a, b in runs)
        reason = _gaps_reason(mdata)
        for a, b in runs:
            cur.execute(
                "INSERT INTO coverage(scope, missing_from, missing_to,"
                " missing_count, status, note) VALUES('global',?,?,?,"
                "'backfill_pending',?)",
                (a, b, b - a + 1, reason))
        self.global_missing = (runs, missing_total)

        # coverage: per volume — missing within its declared span, annotated
        # when other volumes cover those item_index values
        for v in corpus.get("volumes") or []:
            vid = v["volume_id"]
            span = v.get("item_index_span") or [None, None]
            vmin, vmax = int(span[0]), int(span[1])
            own = self.vol_ii[vid]
            for a, b in _runs_of_missing(own, vmin, vmax):
                covered_by = {}
                for x in range(a, b + 1):
                    for other in vol_ids:
                        if other != vid and x in self.vol_ii[other]:
                            covered_by.setdefault(other, []).append(x)
                covered_ranges = {o: _runs_of(xs)
                                  for o, xs in covered_by.items()}
                fully = bool(covered_by) and all(
                    x in present and x not in own
                    for x in range(a, b + 1))
                if covered_by:
                    status = "covered_by_other_volume" if fully \
                        else "partial_other_volume"
                else:
                    status = "backfill_pending"
                cur.execute(
                    "INSERT INTO coverage(scope, missing_from, missing_to,"
                    " missing_count, status, note) VALUES(?,?,?,?,?,?)",
                    (vid, a, b, b - a + 1, status,
                     json.dumps({"covered_by": covered_ranges},
                                ensure_ascii=False) if covered_by else None))

    # -- pass 5: dup_of fix-up ------------------------------------------------
    def _dup_of_pass(self, conn):
        cur = conn.cursor()
        for ii, rows in self.ii_rows.items():
            if len(rows) < 2:
                continue
            anchors = sorted((r for r in rows if r[0] == 0),
                             key=lambda r: r[1])
            for dup_rank, page_id, _vol in sorted(rows,
                                                  key=lambda r: (r[0], r[1])):
                if dup_rank > 0 and anchors:
                    cur.execute("UPDATE pages SET dup_of=? WHERE page_id=?",
                                (anchors[0][1], page_id))
        self.dup_values = sum(1 for r in self.ii_rows.values() if len(r) > 1)
        self.dup_extra_rows = sum(len(r) - 1 for r in self.ii_rows.values())

    # -- validation vs manifest (invariant 6) --------------------------------
    def _validate(self, conn, corpus, mdata, mstats, mtrunc):
        _expect(self.page_count == int(mstats.get("page_count", -1)),
                "page count %d != manifest %s"
                % (self.page_count, mstats.get("page_count")))
        expected_classes = mstats.get("semantic", {}).get("class_counts")
        if expected_classes is not None:
            for k, v in expected_classes.items():
                _expect(self.class_counts.get(k, 0) == int(v),
                        "class %s: %d != manifest %s"
                        % (k, self.class_counts.get(k, 0), v))
            for k in self.class_counts:
                _expect(k in expected_classes,
                        "unexpected record_class %r" % k)
        qfc = mstats.get("quality_flag_counts") or {}
        for k, v in qfc.items():
            _expect(self.flag_counts.get(k, 0) == int(v),
                    "quality flag %s: %d != manifest %s"
                    % (k, self.flag_counts.get(k, 0), v))
        for k in self.flag_counts:
            _expect(k in qfc, "unexpected quality flag %r" % k)
        dup = mstats.get("duplicates") or {}
        if "item_index_values" in dup:
            _expect(self.dup_values == int(dup["item_index_values"]),
                    "dup item_index values %d != manifest %s"
                    % (self.dup_values, dup["item_index_values"]))
        if "item_index_extra_rows" in dup:
            _expect(self.dup_extra_rows == int(dup["item_index_extra_rows"]),
                    "dup extra rows %d != manifest %s"
                    % (self.dup_extra_rows, dup["item_index_extra_rows"]))
        ii_stats = mstats.get("item_index") or {}
        if ii_stats.get("missing_runs") is not None:
            _expect([list(r) for r in self.global_missing[0]] ==
                    [list(r) for r in ii_stats["missing_runs"]],
                    "missing runs %r != manifest %r"
                    % (self.global_missing[0], ii_stats["missing_runs"]))
        if ii_stats.get("missing_count") is not None:
            _expect(self.global_missing[1] == int(ii_stats["missing_count"]),
                    "missing count %d != manifest %s"
                    % (self.global_missing[1], ii_stats["missing_count"]))
        if ii_stats.get("distinct") is not None:
            _expect(len(self.ii_rows) == int(ii_stats["distinct"]),
                    "distinct item_index %d != manifest %s"
                    % (len(self.ii_rows), ii_stats["distinct"]))
        if ii_stats.get("min") is not None:
            _expect(self.min_ii == int(ii_stats["min"]),
                    "item_index min %r != manifest %s"
                    % (self.min_ii, ii_stats["min"]))
        if ii_stats.get("max") is not None:
            _expect(self.max_ii == int(ii_stats["max"]),
                    "item_index max %r != manifest %s"
                    % (self.max_ii, ii_stats["max"]))
        affected = (mtrunc or {}).get("affected_pages")
        if affected is not None:
            _expect(self.truncated_ids == set(affected),
                    "truncated page set mismatch with corpus.json "
                    "semantic.truncation.affected_pages")

    # -- build_meta.db (separate file → can hold the main db sha) ------------
    def _write_build_meta(self, db_sha, source_files, corpus, mdata):
        meta_path = os.path.join(self.out_dir, "build_meta.db")
        conn = sqlite3.connect(meta_path)
        try:
            conn.execute("PRAGMA page_size=4096")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("CREATE TABLE build_meta(key TEXT PRIMARY KEY,"
                         " value TEXT NOT NULL)")
            sem = corpus.get("semantic") or {}
            hc = sem.get("hidden_context") or {}
            tl = _dig(mdata, "stats", "text_len") or {}
            rows = [
                ("corpus_version", self._version()),
                ("content_sha256", str(mdata.get("content_sha256"))),
                ("schema_version", SCHEMA_VERSION),
                ("topic_norm_version", TOPIC_NORM_VERSION),
                ("tokenizer_version", TOKENIZER_VERSION),
                ("built_at", time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime())),
                ("db_sha256", db_sha),
                ("page_count", str(self.page_count)),
                ("heading_count", str(self.heading_count)),
                ("topic_count", str(self.topic_count)),
                ("volume_count", str(self.volume_count)),
                ("rag_status", RAG_STATUS),
                ("surah_status", "not_supported"),
                ("hidden_context_included", "false"),
                ("policy", str(hc.get("policy") or "")),
                ("page_content_hash_note",
                 "content_hash is a crawler-side hash (not reproducible "
                 "from page text; probe PCM-20.6.4); stored verbatim as "
                 "content_sha256"),
                ("fts_note",
                 "standalone FTS5 table; tokens pre-computed with "
                 "tokenize_fa/1.0 (diacritics deleted, ZWNJ to space, "
                 "digits to ASCII); unicode61; prefix AND queries; no "
                 "Persian stemming (documented limitation)"),
                ("text_length_stats", json.dumps(
                    {k: tl.get(k) for k in ("p50", "p90", "p99", "max")},
                    ensure_ascii=False)),
                ("source_files", json.dumps(source_files,
                                            ensure_ascii=False)),
            ]
            conn.executemany("INSERT INTO build_meta(key,value) VALUES(?,?)",
                             rows)
            conn.commit()
        finally:
            conn.close()

    def _write_sidecars(self, db_sha):
        meta_path = os.path.join(self.out_dir, "build_meta.db")
        meta_sha = sha256_file(meta_path)
        with open(os.path.join(self.out_dir, "build.sha256"), "w",
                  encoding="utf-8") as f:
            f.write("%s  tasnim_readmodel.db\n" % db_sha)
            f.write("%s  build_meta.db\n" % meta_sha)

    def _write_covers(self, corpus):
        from tasnim.web.cover import generate_cover
        work = (corpus.get("work") or {}).get("work_name", "")
        edition = (corpus.get("edition") or {}).get("edition_name", "")
        for v in corpus.get("volumes") or []:
            vid = v["volume_id"]
            svg = generate_cover(vid, v.get("volume_no"), work, edition)
            with open(os.path.join(self.out_dir, "covers",
                                   "%s.svg" % vid), "w", encoding="utf-8") as f:
                f.write(svg)

    def _version(self):
        base = os.path.basename(self.corpus_dir.rstrip("/\\"))
        return base if re.fullmatch(r"v\d+", base) else "unknown"

    def _report(self, corpus, mdata, db_sha, t0):
        meta_sha = sha256_file(os.path.join(self.out_dir, "build_meta.db"))
        return {
            "corpus_version": self._version(),
            "corpus_dir": self.corpus_dir,
            "out_dir": self.out_dir,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(t0)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                         time.gmtime()),
            "duration_s": round(time.time() - t0, 2),
            "content_sha256": mdata.get("content_sha256"),
            "db_sha256": db_sha,
            "build_meta_sha256": meta_sha,
            "db_size_bytes": os.path.getsize(os.path.join(
                self.out_dir, "tasnim_readmodel.db")),
            "counts": {
                "pages": self.page_count,
                "headings": self.heading_count,
                "topics": self.topic_count,
                "volumes": self.volume_count,
                "missing_item_index": self.global_missing[1],
                "missing_runs": [list(r) for r in self.global_missing[0]],
                "dup_item_index_values": self.dup_values,
            },
            "opened_files": sorted(set(self.opened_files)),
            "invariants": {
                "source_read_only": True,
                "forbidden_files_opened": [
                    f for f in sorted(set(self.opened_files))
                    if f in FORBIDDEN_SOURCE_FILES],
                "hidden_context_included": False,
                "deterministic": "verified by test (two builds, same SHA)",
            },
        }

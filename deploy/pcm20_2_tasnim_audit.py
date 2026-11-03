#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pcm20_2_tasnim_audit.py — ممیزی عمیق read-only خروجی تسنیم (PCM-20.2).

اجرا روی s52 (بدون هیچ تغییر؛ فقط خواندن فایل‌های خروجی PCM-20):

    python3 deploy/pcm20_2_tasnim_audit.py \
        --jsonl /home/saber/tasnim-export/tasnim-corpus.jsonl \
        [--json  /home/saber/tasnim-export/tasnim-corpus.json] \
        [--out   /home/saber/tasnim-export/pcm20_2_audit.json]

چه کار می‌کند (همه روی همان فایل ۴۵٬۸۴۴ سندی که PCM-20 ساخت):
  A. نمونه‌برداری: ۱۰ رکورد از ابتدا، ۱۰ از وسط، ۱۰ از انتها (با truncation متن)
  B. ممیزی صحت: رکوردهای ناقص (فیلد null/خالی)، متن‌های خالی/کوتاه،
     item_index تکراری (با رکوردهای متناظر و URLهایشان)، content_hash تکراری
  C. تحلیل حفره: بازه‌های پیوسته missing/present + توزیع اندازه حفره‌ها
  D. ساختار جلد: group-by بر section= (URL)، تعداد جلد، صفحات/محدوده
     item_index و barg هر جلد، تکرار barg بین جلد، نمونه URL هر جلد
خروجی: یک فایل JSON (audit) + خلاصه console. هیچ چیز دیگری لمس نمی‌شود.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import parse_qs, urlparse

# Persian digits U+06F0..U+06F9 + Arabic-Indic U+0660..U+0669 (code points, no glyph strings).
_DIGIT_MAP = {}
for _i in range(10):
    _DIGIT_MAP[chr(0x06F0 + _i)] = str(_i)
    _DIGIT_MAP[chr(0x0660 + _i)] = str(_i)
DIGITS_RE = re.compile(r"\d+")
SECTION_RE = re.compile(r"(\d+)\s*\)?$")       # عدد آخرِ section (مثلا «تفسیر تسنیم جلد (80)»)
VOL_LABEL_RE = re.compile(r"جلد")


def force_utf8_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def to_ascii(value: str) -> str:
    return "".join(_DIGIT_MAP.get(c, c) for c in value)


def section_of(url: str) -> str:
    qs = parse_qs(urlparse(url or "").query)
    return (qs.get("section") or [""])[0].strip()


def volume_no_from_section(section: str):
    """شماره جلد از section (عدد آخر)؛ اگر نبود/نامشخص بود None."""
    s = to_ascii(section)
    if not s:
        return None
    m = SECTION_RE.search(s)
    return int(m.group(1)) if m else None


def text_of(rec: dict) -> str:
    v = rec.get("values") or {}
    t = v.get("متن")
    return t if isinstance(t, str) else ""


def reparsed_barg(rec: dict):
    """بازپارس صحیح «برگ»: همه‌ی ریک‌های ارقام بعد از نرمال‌سازی ارقام (حذف
    جداکننده‌ی هزارگان ٬/, — برخلاف parse_barg که فقط اولین ریک را می‌گرفت)."""
    v = rec.get("values") or {}
    raw = v.get("برگ")
    if raw is None:
        return None
    runs = DIGITS_RE.findall(to_ascii(str(raw)))
    if not runs:
        return None
    try:
        return int("".join(runs))
    except ValueError:
        return None


def runs(sorted_numbers) -> list:
    """پیوسته‌سازی اعداد مرتب‌شده به بازه‌های [lo, hi]."""
    out = []
    for n in sorted_numbers:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def main(argv=None) -> int:
    force_utf8_stdio()
    ap = argparse.ArgumentParser(description="Read-only deep audit of Tasnim corpus export (PCM-20.2)")
    ap.add_argument("--jsonl", required=True, help="tasnim-corpus.jsonl از خروجی PCM-20")
    ap.add_argument("--json", default=None, help="(اختیاری) tasnim-corpus.json برای هدر/پاسچک")
    ap.add_argument("--out", default=None, help="مسیر خروجی audit JSON (پیش‌فرض کنار jsonl)")
    ap.add_argument("--sample-per-end", type=int, default=10)
    args = ap.parse_args(argv)

    if not os.path.exists(args.jsonl):
        print("JSONL not found: %s" % args.jsonl, file=sys.stderr)
        return 2

    # ---------------- load ----------------
    records = []
    with open(args.jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    n = len(records)
    n_mid = n // 2

    # ---------------- A. samples ----------------
    idx_ends = [i for i in range(0, n, max(1, n // args.sample_per_end))][:args.sample_per_end]
    idx_mid = [n_mid + (i - args.sample_per_end // 2) for i in range(args.sample_per_end)]
    idx_end = list(range(n - args.sample_per_end, n))
    sample_ids = sorted(set(idx_ends + idx_mid + idx_end))
    samples = []
    for i in sample_ids:
        r = records[i]
        v = r.get("values") or {}
        t = text_of(r)
        samples.append({
            "pos": i, "where": "start" if i < n // 3 else ("end" if i >= 2 * n // 3 else "middle"),
            "page_id": r.get("page_id"), "url": r.get("url"),
            "item_index": r.get("item_index"), "barg": r.get("barg"),
            "captured_at": r.get("captured_at"),
            "content_hash": r.get("content_hash"),
            "text_len": len(t),
            "text_head": t[:200],
            "keys_values": sorted(v.keys()),
            "nav_next": (v.get("لینک صفحه بعد") or None),
            "nav_prev": (v.get("لینک صفحه قبل") or None),
            "address": (v.get("ادرس صفحه") or None),
            "barg_raw": (v.get("برگ") or None),
        })

    # ---------------- B. integrity ----------------
    incomplete, empty_text, short_text = [], [], 0
    text_lens = []
    for i, r in enumerate(records):
        v = r.get("values") or {}
        miss = [k for k in ("page_id", "url", "captured_at", "content_hash") if r.get(k) in (None, "")]
        if r.get("item_index") is None:
            miss.append("item_index")
        if not v:
            miss.append("values(empty)")
        t = text_of(r)
        if not t.strip():
            miss.append("values.متن(empty)")
        if miss:
            incomplete.append({"pos": i, "page_id": r.get("page_id"), "url": r.get("url"),
                               "missing": miss})
        if not t.strip():
            empty_text.append({"pos": i, "page_id": r.get("page_id"),
                               "item_index": r.get("item_index"), "url": r.get("url")})
        elif len(t.strip()) < 20:
            short_text += 1
        text_lens.append(len(t))

    # item_index duplicates (with the full records)
    by_idx = defaultdict(list)
    for i, r in enumerate(records):
        ix = r.get("item_index")
        if ix is not None:
            by_idx[ix].append(i)
    dup_idx = {}
    for ix, pos in sorted(by_idx.items()):
        if len(pos) > 1:
            dup_idx[ix] = [{
                "pos": p, "page_id": records[p].get("page_id"),
                "url": records[p].get("url"),
                "content_hash": records[p].get("content_hash"),
                "barg": records[p].get("barg"),
                "section": section_of(records[p].get("url") or ""),
                "captured_at": records[p].get("captured_at"),
            } for p in pos]

    # content_hash duplicates
    by_hash = defaultdict(list)
    for i, r in enumerate(records):
        h = r.get("content_hash")
        if h:
            by_hash[h].append(i)
    dup_hash = {h: [
        {"pos": p, "page_id": records[p].get("page_id"),
         "item_index": records[p].get("item_index"),
         "url": records[p].get("url")} for p in ps
    ] for h, ps in by_hash.items() if len(ps) > 1}

    # ---------------- B2. barg reparse check ----------------
    # PCM-20 parse_barg kept only the FIRST digit run of the raw barg string
    # (e.g. "39,005" with Persian digits -> 39). reparsed_barg joins ALL runs,
    # so we can measure the real barg value and its relation to item_index.
    BARG_KEY = "\u0628\u0631\u06af"
    barg_with_raw = 0
    barg_diff_count = 0
    barg_diff_samples = []
    barg_eq_ix1 = 0
    for i, r in enumerate(records):
        raw = (r.get("values") or {}).get(BARG_KEY)
        if raw is None:
            continue
        barg_with_raw += 1
        rp = reparsed_barg(r)
        ex = r.get("barg")
        if rp != ex:
            barg_diff_count += 1
            if len(barg_diff_samples) < 10:
                barg_diff_samples.append({"pos": i, "item_index": r.get("item_index"),
                                          "raw": str(raw), "export_barg": ex, "reparsed": rp})
        if rp is not None and r.get("item_index") is not None and rp == r["item_index"] + 1:
            barg_eq_ix1 += 1
    barg_check = {
        "with_raw_barg": barg_with_raw,
        "reparsed_differs_from_export_barg": barg_diff_count,
        "sample_mismatches": barg_diff_samples,
        "reparsed_equals_item_index_plus_1": barg_eq_ix1,
    }

    # ---------------- C. gaps ----------------
    idx_numbers = sorted(x for x in (r.get("item_index") for r in records) if x is not None)
    lo, hi = idx_numbers[0], idx_numbers[-1]
    present = set(idx_numbers)
    missing = [x for x in range(lo, hi + 1) if x not in present]
    pres_runs = runs(sorted(present))
    miss_runs = runs(missing)
    miss_sizes = Counter(hi_ - lo_ + 1 for lo_, hi_ in miss_runs)
    big_miss = [{"lo": a, "hi": b, "size": b - a + 1} for a, b in miss_runs if b - a + 1 >= 50]

    # ---------------- D. volumes ----------------
    by_sec = defaultdict(list)
    for i, r in enumerate(records):
        by_sec[section_of(r.get("url") or "")].append(i)

    def sec_stats(sec, pos):
        idxs = [records[p].get("item_index") for p in pos]
        idxs = [x for x in idxs if x is not None]
        bargs = [r_ for r_ in (records[p].get("barg") for p in pos) if r_ is not None]
        return {
            "pages": len(pos),
            "item_index_min": min(idxs) if idxs else None,
            "item_index_max": max(idxs) if idxs else None,
            "item_index_span": (max(idxs) - min(idxs) + 1) if idxs else 0,
            "item_index_gaps_in_span": (len(idxs) - len(set(idxs))) if idxs else 0,
            "barg_min": min(bargs) if bargs else None,
            "barg_max": max(bargs) if bargs else None,
            "barg_distinct": len(set(bargs)),
            "no_item_index": sum(1 for x in idxs if x is None),
            "empty_text": sum(1 for p in pos if not text_of(records[p]).strip()),
        }

    volumes = []
    for sec, pos in sorted(by_sec.items(), key=lambda kv: (volume_no_from_section(kv[0]) is None,
                                                           volume_no_from_section(kv[0]) or 0, kv[0])):
        st = sec_stats(sec, pos)
        volumes.append({
            "section": sec,
            "volume_no": volume_no_from_section(sec),
            "sample_url": records[pos[0]].get("url"),
            **st,
        })

    # barg repeats across volumes: for a few frequent barg values, which volumes own them
    barg_owners = defaultdict(set)
    for sec, pos in by_sec.items():
        for p in pos:
            b = records[p].get("barg")
            if b is not None:
                barg_owners[b].add(volume_no_from_section(sec))
    barg_cross_volume = {str(b): sorted(v for v in vs if v is not None)
                         for b, vs in list(barg_owners.items())[:5] if len(vs) > 1}

    # ---------------- header patchcheck (optional .json) ----------------
    header_patch = None
    if args.json and os.path.exists(args.json):
        with open(args.json, "r", encoding="utf-8") as f:
            head = f.read(8000)
        header_patch = {
            "first_8k_bytes_sha256": hashlib.sha256(head.encode("utf-8")).hexdigest(),
            "looks_like_object": head.lstrip()[:1] == "{",
            "has_pages_key": '"pages"' in head,
        }

    # ---------------- output ----------------
    textl = sorted(text_lens)
    def pct(p):
        return textl[min(n - 1, int(p * n))] if n else 0
    audit = {
        "document_count": n,
        "samples": samples,
        "integrity": {
            "records_with_missing_fields": len(incomplete),
            "incomplete_records": incomplete[:50],
            "empty_text_count": len(empty_text),
            "empty_text_records": empty_text[:50],
            "text_lt_20_chars_count": short_text,
            "text_len_min": textl[0] if n else None,
            "text_len_p50": pct(0.5), "text_len_p90": pct(0.9),
            "text_len_max": textl[-1] if n else None,
            "item_index_duplicates": {"count": len(dup_idx), "details": dup_idx},
            "content_hash_duplicates": {
                "count": len(dup_hash),
                "details": {h: d for h, d in list(dup_hash.items())[:20]},
            },
            "barg_reparse_check": barg_check,
        },
        "gaps": {
            "range": [lo, hi], "range_size": hi - lo + 1,
            "present_count": len(idx_numbers), "present_runs": pres_runs,
            "missing_count": len(missing), "missing_runs": miss_runs,
            "missing_size_distribution": dict(sorted(miss_sizes.items())),
            "big_missing_runs_ge_50": big_miss,
            "cursor_note": "cursor_url زنده API = item_index 91285 (جلد 80) — بالاتر از max موجود",
        },
        "volumes": {
            "distinct_sections": len(volumes),
            "sections_with_volume_no": sum(1 for v in volumes if v["volume_no"] is not None),
            "volume_nos": sorted(v["volume_no"] for v in volumes if v["volume_no"] is not None),
            "per_volume": volumes,
            "barg_cross_volume_examples": barg_cross_volume,
        },
        "header_patchcheck": header_patch,
    }

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.jsonl)), "pcm20_2_audit.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(audit, f, ensure_ascii=False, indent=1)

    print("\n=== PCM-20.2 AUDIT DONE (read-only) ===")
    print("documents        : %d" % n)
    print("incomplete       : %d records (first 50 in file)" % len(incomplete))
    print("empty text       : %d ; <20 chars: %d ; text len p50/p90/max: %s/%s/%s"
          % (len(empty_text), short_text, pct(0.5), pct(0.9), textl[-1] if n else None))
    print("dup item_index   : %d values / %d extra rows" % (len(dup_idx), sum(len(v) - 1 for v in dup_idx.values())))
    print("dup content_hash : %d values / %d extra rows" % (len(dup_hash), sum(len(v) - 1 for v in dup_hash.values())))
    print("barg reparse     : %d with raw barg ; %d differ from export barg ; %d == item_index+1"
          % (barg_with_raw, barg_diff_count, barg_eq_ix1))
    print("item_index range : %d..%d (size %d) ; present %d ; missing %d (%d runs, %d big>=50)"
          % (lo, hi, hi - lo + 1, len(idx_numbers), len(missing), len(miss_runs), len(big_miss)))
    vnos = audit["volumes"]["volume_nos"]
    vnos_str = ("%s..%s" % (vnos[0], vnos[-1])) if vnos else "none"
    print("sections/volumes : %d distinct ; with volume_no: %d ; vol_nos: %s (%d)"
          % (len(volumes), audit["volumes"]["sections_with_volume_no"], vnos_str, len(vnos)))
    print("audit file       : %s (%d bytes)  sha256=%s"
          % (out, os.path.getsize(out),
             hashlib.sha256(open(out, "rb").read()).hexdigest()))
    print("DONE — read-only; no files were modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

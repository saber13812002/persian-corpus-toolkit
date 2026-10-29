"""factory.corpus — PCM-16: پیکره‌ساز (Corpus Builder) — قرارداد c-1.

تبدیل Dumpهای معتبر (دفاع d-1) به یک پیکره‌ی متن فارسی قابل‌انتقال:

    <out-dir>/
      corpus-manifest.json     ← این ماژول (قرارداد c-1)
      raw.jsonl                ← جریان RAW (هر بلوک: متن خام + provenance)
      normalized.jsonl         ← جریان NORMALIZED (هر بلوک: متن نرمال + provenance)
      raw.unique.jsonl         ← بدون‌تکرار RAW (کلید: sha256(raw_text)[:16])
      normalized.unique.jsonl  ← بدون‌تکرار NORMALIZED (کلید: content_hash)
      corpus-data.zip          ← آرشیو قطعی (deterministic) ۴ فایل JSONL
      hf-package/
        README.md              ← کارت داده‌ی Hugging Face (فقط محلی — بارگذاری ممنوع)
        corpus-manifest.json   ← کپی مانیفست (برای اعتبارسنجی در بستر مصرف)
        raw.jsonl / normalized.jsonl / raw.unique.jsonl / normalized.unique.jsonl

قواعد طراحی (PCM-16 — ادامه‌ی مستقیم قرارداد d-1):
- ورودی **فقط** دایرکتوری‌های Dump d-1 است؛ هر Dump پیش از **هر** نگارش باید
  `validate_dump` را بگذراند (V1..V11)؛ هر Dump نامعتبر → CorpusError بدون
  هیچ خروجی (fail-fast پیش از write).
- تابع خالص و فقط‌خوانده از Dumpها؛ بدون DB، بدون Flask، بدون ES، بدون LLM،
  بدون شبکه (هیچ import شبکه‌ای در این ماژول نیست).
- RAW و NORMALIZED دو جریان **جدا** هستند: RAW هرگز با نسخه‌ی نرمال‌شده
  جایگزین نمی‌شود؛ هر خط هر دو متن خود را در فایل مخصوصش دارد.
- dedup بین فایل‌ها با کلید hash متن؛ استراتژی first-occurrence در ترتیب
  قطعی؛ شمارش و فهرست تکرارها (`occurrence_count`/`occurrences`) در همان
  خط ثبت می‌شود — هیچ provenance‌ای حذف نمی‌شود.
- provenance کامل برای هر بلوک: SHA-256 فایل docx ورودی، factory file_id،
  work/edition/volume، hash فایل blocks.jsonl و dump-manifest.json خود Dump،
  نسخه‌های p/n/m/schema/factory و policy نرمال‌سازی ثبت‌شده.
- determinism: ترتیب دامپ‌ها = (input_sha256, factory_file_id)؛ ترتیب
  بلوک‌ها = block_index؛ ۴ فایل JSONL و آرشیو ZIP بین اجراها
  **بایت‌به‌بایت** یکسان (تنها ناپایدار: `generated_at` در manifest/README).
- idempotent: build دوباره روی همان out_dir → بازنویسی درجا، بدون فایل
  تکراری، بدون تغییر hash داده‌ها.
- آمار: فقط شمارنده‌های واقعی داده (تعداد خطوط/کاراکتر/بلوک‌ها از خود
  جریان‌ها محاسبه می‌شود — هیچ عدد تخمینی/ساختگی).
- HF: فقط ساخت **پکیج محلی** آماده (README + داده‌ها)؛ هیچ کد بارگذاری و
  هیچ دسترسی شبکه‌ای در این ماژول وجود ندارد.
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile

from .dump import DUMP_VERSION, validate_dump
from .errors import FactoryError
from .models import FACTORY_VERSION, content_hash, utc_now_iso

CORPUS_VERSION = "c-1"

#: ترتیب قطعی فایل‌های داده‌ای پیکره (در manifest و آرشیو)
CORPUS_DATA_FILES = (
    "raw.jsonl",
    "normalized.jsonl",
    "raw.unique.jsonl",
    "normalized.unique.jsonl",
)

ARCHIVE_NAME = "corpus-data.zip"
HF_DIR = "hf-package"


class CorpusError(FactoryError):
    """ورودی نامعتبر (Dump ناتایید/ناقص/غیرمنطبق) یا خطای ساخت پیکره."""

    code = "corpus_error"


# ---------------------------------------------------------------------------
# ابزارهای داخلی
# ---------------------------------------------------------------------------

def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_blocks(dump_dir: str) -> list[dict]:
    """خواندن blocks.jsonl یک Dump (اعتبار JSON توسط validate_dump تضمین شده)."""
    p = os.path.join(dump_dir, "blocks.jsonl")
    recs = []
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f.read().splitlines(), 1):
            if not line.strip():
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise CorpusError(
                    f"blocks.jsonl خط {i}: JSON نامعتبر", error=str(e))
    return recs


def _deterministic_zip(path: str, members: list[tuple[str, bytes]]) -> None:
    """ZIP قطعی: ترتیب ثابت (ترتیب داده‌شده)، timestamp ثابت 1980-01-01،
    deflate سطح 9 — بایت‌به‌بایت قابل‌تکرار."""
    with zipfile.ZipFile(path, "w",
                         compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        for name, data in members:
            zi = zipfile.ZipInfo(filename=name,
                                 date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)


# ---------------------------------------------------------------------------
# ساخت پیکره
# ---------------------------------------------------------------------------

def build_corpus(dump_dirs: list[str], out_dir: str,
                 require_quality: str | None = None) -> dict:
    """ساخت پیکره (قرارداد c-1) از روی Dumpهای معتبر d-1.

    dump_dirs:   دایرکتوری‌های Dump (هرکدام باید validate_dump را بگذراند)
    out_dir:     مقصد پیکره (ساخت/بازنویسی درجا — idempotent)
    require_quality: None (پیش‌فرض) = همه‌ی دامپ‌های تاییدشده؛ "ok" = فقط
        دامپ‌هایی با quality_status == "ok"

    برگشت: dict همان corpus-manifest.json

    خطا: CorpusError — اگر هر Dump نامعتبر باشد، دایرکتوری وجود نداشته
    باشد، یا quality gate رد شود. **پیش از هر خطا هیچ فایلی نوشته نمی‌شود.**
    """
    if require_quality not in (None, "ok"):
        raise CorpusError(
            "require_quality باید None یا 'ok' باشد",
            got=require_quality)
    for d in dump_dirs:
        if not d or not os.path.isdir(os.path.abspath(d)):
            raise CorpusError(f"دایرکتوری Dump پیدا نشد: {d!r}")

    # --- مرحله ۱: اعتبارسنجی **تمام** دامپ‌ها پیش از هر نگارش ------------
    infos = []
    for d in dump_dirs:
        d = os.path.abspath(d)
        ok, errors, _warnings = validate_dump(d)
        if not ok:
            raise CorpusError(
                f"Dump نامعتبر رد شد: {d} — {'; '.join(errors[:5])}",
                dump=d, errors=errors)
        dm = _load_json(os.path.join(d, "dump-manifest.json"))
        qstatus = (dm.get("quality") or {}).get("quality_status")
        if require_quality == "ok" and qstatus != "ok":
            raise CorpusError(
                f"quality gate: quality_status دامپ {d} = {qstatus!r} "
                f"(درخواست: 'ok')",
                dump=d, quality_status=qstatus)
        blocks = _read_blocks(d)
        file_sha = {e.get("name"): e.get("sha256")
                    for e in dm.get("files") or []}
        infos.append({
            "dir": d,
            "dm": dm,
            "blocks": blocks,
            "blocks_sha256": file_sha.get("blocks.jsonl"),
            "manifest_sha256": _sha256(os.path.join(d, "dump-manifest.json")),
        })

    # ترتیب قطعی دامپ‌ها (مستند در manifest.policy)
    infos.sort(key=lambda i: (
        (i["dm"].get("integrity") or {}).get("input_sha256") or "",
        (i["dm"].get("identifiers") or {}).get("file_id") or ""))

    # --- مرحله ۲: ساخت جریان‌ها + dedup -----------------------------------
    raw_lines: list[dict] = []
    norm_lines: list[dict] = []
    raw_unique: dict[str, dict] = {}
    norm_unique: dict[str, dict] = {}
    by_type: dict[str, int] = {}
    quality_hist: dict[str, int] = {}
    input_dumps: list[dict] = []

    for info in infos:
        dm = info["dm"]
        ident = dm.get("identifiers") or {}
        src = (dm.get("source") or {}).get("input_file") or {}
        integrity = dm.get("integrity") or {}
        doc = dm.get("document") or {}
        versions = dm.get("versions") or {}
        q = dm.get("quality") or {}
        qstatus = q.get("quality_status") or "unknown"
        quality_hist[qstatus] = quality_hist.get(qstatus, 0) + 1

        raw_chars = 0
        norm_chars = 0
        for rec in info["blocks"]:
            bid = rec.get("block_id")
            btype = rec.get("type")
            raw_t = rec.get("raw_text", "")
            norm_t = rec.get("normalized_text", "")
            chash = rec.get("content_hash")
            by_type[btype] = by_type.get(btype, 0) + 1
            raw_chars += len(raw_t)
            norm_chars += len(norm_t)

            prov = {
                "input_sha256": integrity.get("input_sha256"),
                "input_filename": src.get("filename"),
                "factory_file_id": ident.get("file_id"),
                "work_id": ident.get("work_id"),
                "edition_id": ident.get("edition_id"),
                "volume_id": ident.get("volume_id"),
                "dump_dir": info["dir"],
                "dump_contract": dm.get("dump_contract_version"),
                "dump_blocks_sha256": info["blocks_sha256"],
                "dump_manifest_sha256": info["manifest_sha256"],
                "versions": versions,
            }
            document = {
                "title": doc.get("title"),
                "author": doc.get("author"),
                "publisher": doc.get("publisher"),
                "publish_year": doc.get("publish_year"),
                "volume_no": doc.get("volume_no"),
                "language": doc.get("language"),
            }
            record_id = f"cb1:{(integrity.get('input_sha256') or '')[:12]}:{bid}"
            where = f"{(integrity.get('input_sha256') or '')[:8]}:{bid}"

            # --- جریان RAW (متن خام، دست‌نخورده) ---
            r_line = {
                "record_id": record_id,
                "block_id": bid,
                "block_index": rec.get("block_index"),
                "type": btype,
                "raw_text": raw_t,
                "provenance": prov,
                "document": document,
            }
            raw_lines.append(r_line)
            r_key = "sha256:" + _sha256_bytes(raw_t.encode("utf-8"))[:16]
            u = raw_unique.get(r_key)
            if u is None:
                u = dict(r_line)
                u["raw_hash"] = r_key
                u["occurrence_count"] = 0
                u["occurrences"] = []
                raw_unique[r_key] = u
            u["occurrence_count"] += 1
            u["occurrences"].append(where)

            # --- جریان NORMALIZED ---
            n_line = {
                "record_id": record_id,
                "block_id": bid,
                "block_index": rec.get("block_index"),
                "type": btype,
                "normalized_text": norm_t,
                "norm_version": rec.get("norm_version"),
                "content_hash": chash,
                "provenance": prov,
                "document": document,
            }
            norm_lines.append(n_line)
            u = norm_unique.get(chash)
            if u is None:
                u = dict(n_line)
                u["occurrence_count"] = 0
                u["occurrences"] = []
                norm_unique[chash] = u
            u["occurrence_count"] += 1
            u["occurrences"].append(where)

        n_blocks = len(info["blocks"])
        input_dumps.append({
            "dir": info["dir"],
            "file_id": ident.get("file_id"),
            "input_sha256": integrity.get("input_sha256"),
            "input_filename": src.get("filename"),
            "work_id": ident.get("work_id"),
            "edition_id": ident.get("edition_id"),
            "volume_id": ident.get("volume_id"),
            "dump_contract": dm.get("dump_contract_version"),
            "dump_blocks_sha256": info["blocks_sha256"],
            "dump_manifest_sha256": info["manifest_sha256"],
            "versions": versions,
            "quality": {
                "status": q.get("status"),
                "score": q.get("score"),
                "quality_status": q.get("quality_status"),
            },
            "document": {
                "title": doc.get("title"),
                "author": doc.get("author"),
                "publisher": doc.get("publisher"),
                "publish_year": doc.get("publish_year"),
                "volume_no": doc.get("volume_no"),
                "language": doc.get("language"),
            },
            "counts": {
                "blocks": n_blocks,
                "raw_chars": raw_chars,
                "normalized_chars": norm_chars,
            },
        })

    raw_unique_lines = list(raw_unique.values())
    norm_unique_lines = list(norm_unique.values())

    # --- مرحله ۳: نگارش (پس از موفقیت کامل مراحل ۱ و ۲) -------------------
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    _write_jsonl(os.path.join(out_dir, "raw.jsonl"), raw_lines)
    _write_jsonl(os.path.join(out_dir, "normalized.jsonl"), norm_lines)
    _write_jsonl(os.path.join(out_dir, "raw.unique.jsonl"), raw_unique_lines)
    _write_jsonl(os.path.join(out_dir, "normalized.unique.jsonl"),
                 norm_unique_lines)

    # آرشیو قطعی = ۴ فایل JSONL (بدون مانیفست تا self-hash ممکن باشد)
    archive_path = os.path.join(out_dir, ARCHIVE_NAME)
    _deterministic_zip(archive_path, [
        (name, _read_bytes(os.path.join(out_dir, name)))
        for name in CORPUS_DATA_FILES
    ])

    manifest = {
        "corpus_contract_version": CORPUS_VERSION,
        "generated_at": utc_now_iso(),
        "generator": f"word-factory/{FACTORY_VERSION}",
        "policy": {
            "streams": ["raw", "normalized"],
            "raw_kept_byte_exact": True,
            "dedup_key_raw": "sha256(raw_text)[:16]",
            "dedup_key_normalized": "content_hash = sha256(normalized_text)[:16]",
            "dedup_strategy": "first_occurrence_in_deterministic_order",
            "deterministic_order": "dumps: (input_sha256, factory_file_id); "
                                   "blocks: block_index",
            "archive": "zip deflate-9, fixed timestamp 1980-01-01, "
                       "members = 4 JSONL (no manifest — self-hash)",
            "db": "none", "elasticsearch": "none",
            "network": "none", "llm": "none",
        },
        "files": [
            {
                "name": name,
                "sha256": _sha256(os.path.join(out_dir, name)),
                "size_bytes": os.path.getsize(os.path.join(out_dir, name)),
                "line_count": {
                    "raw.jsonl": len(raw_lines),
                    "normalized.jsonl": len(norm_lines),
                    "raw.unique.jsonl": len(raw_unique_lines),
                    "normalized.unique.jsonl": len(norm_unique_lines),
                }[name],
                "encoding": "utf-8",
                "format": "jsonl",
            }
            for name in CORPUS_DATA_FILES
        ],
        "archive": {
            "name": ARCHIVE_NAME,
            "sha256": _sha256(archive_path),
            "size_bytes": os.path.getsize(archive_path),
            "members": list(CORPUS_DATA_FILES),
        },
        "input_dumps": input_dumps,
        "counts": {
            "dumps": len(input_dumps),
            "blocks_total": len(raw_lines),
            "blocks_unique_raw": len(raw_unique_lines),
            "blocks_unique_normalized": len(norm_unique_lines),
            "duplicates_raw": len(raw_lines) - len(raw_unique_lines),
            "duplicates_normalized": len(norm_lines) - len(norm_unique_lines),
            "raw_chars": sum(len(r["raw_text"]) for r in raw_lines),
            "normalized_chars": sum(len(r["normalized_text"]) for r in norm_lines),
            "by_type": dict(sorted(by_type.items())),
            "dumps_by_quality": dict(sorted(quality_hist.items())),
        },
        "integrity": {
            "all_dumps_validated": True,
            "validation_rules": f"dump d-1 (V1..V11)",
        },
    }

    # --- مرحله ۴: پکیج محلی Hugging Face (بدون هیچ بارگذاری) --------------
    hf_path = os.path.join(out_dir, HF_DIR)
    os.makedirs(hf_path, exist_ok=True)
    for name in CORPUS_DATA_FILES:
        with open(os.path.join(hf_path, name), "wb") as g:
            g.write(_read_bytes(os.path.join(out_dir, name)))
    with open(os.path.join(hf_path, "README.md"), "w",
              encoding="utf-8") as f:
        f.write(_hf_readme(manifest))
    manifest["hf_package"] = {
        "dir": HF_DIR,
        "upload": "manual — فقط پکیج محلی ساخته می‌شود (هیچ بارگذاری خودکار)",
        "files": {
            "README.md": _sha256(os.path.join(hf_path, "README.md")),
            **{name: _sha256(os.path.join(hf_path, name))
               for name in CORPUS_DATA_FILES},
        },
    }

    # دو کپی مانیفست بایتی یکسان (همان dict، همان serializer)
    _write_json(os.path.join(hf_path, "corpus-manifest.json"), manifest)
    _write_json(os.path.join(out_dir, "corpus-manifest.json"), manifest)
    return manifest


def _hf_readme(m: dict) -> str:
    """کارت داده‌ی Hugging Face — فقط با آمار واقعی manifest (بدون تخمین)."""
    c = m["counts"]
    lines = [
        "---",
        'language: fa',
        'license: cc-by-nc-sa-4.0',
        'task_categories:',
        '- other',
        'size_categories: n<10K',
        'format: jsonl',
        'modality: text',
        "---",
        "",
        "# Persian Corpus Toolkit — Corpus (c-1)",
        "",
        "پیکره‌ی متون فارسی، ساخته‌شده از روی Dumpهای معتبر قرارداد "
        f"`{DUMP_VERSION}` خط Word Factory (corpus builder {CORPUS_VERSION}).",
        "",
        "## ساختار",
        "",
        "- `raw.jsonl` — جریان RAW: متن دقیق‌الکلمه + provenance کامل (هرگز دست‌نخورده)",
        "- `normalized.jsonl` — جریان NORMALIZED: متن نرمال‌شده با policy ثبت‌شده",
        "- `raw.unique.jsonl` / `normalized.unique.jsonl` — نسخه‌های بدون‌تکرار",
        "  با `occurrence_count` و `occurrences`",
        "- `corpus-manifest.json` — مانیفست نسخه‌شده (hash/size/line_count هر فایل)",
        "",
        "## آمار (محاسبه‌شده از داده — نه تخمین)",
        "",
        f"- دامپ ورودی: `{c['dumps']}`",
        f"- بلوک (کل): `{c['blocks_total']}`",
        f"- بلوک منحصربه‌فرد RAW: `{c['blocks_unique_raw']}` "
        f"(تکرار: `{c['duplicates_raw']}`)",
        f"- بلوک منحصربه‌فرد NORMALIZED: `{c['blocks_unique_normalized']}` "
        f"(تکرار: `{c['duplicates_normalized']}`)",
        f"- کاراکتر RAW: `{c['raw_chars']:,}` · NORMALIZED: `{c['normalized_chars']:,}`",
        "",
        "## provenance",
        "",
        "هر خط شامل `provenance` است: SHA-256 فایل docx ورودی، file_id، "
        "work/edition/volume، hashهای blocks.jsonl و dump-manifest خود Dump و "
        "نسخه‌های parser/normalizer/manifest/schema/factory.",
        "",
        "## بارگذاری",
        "",
        "این پکیج **فقط محلی** آماده می‌شود. هر بارگذاری عمومی (Hugging Face "
        "یا هر جای دیگر) فقط با تأیید صریح مالک داده انجام می‌شود.",
        "",
    ]
    return "\n".join(lines)

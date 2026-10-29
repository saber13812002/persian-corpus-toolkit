"""factory.dump — PCM-14C.3: قرارداد رسمی، نسخه‌پذیر و مستقل از Elasticsearch
برای تبدیل خروجی Word Factory به Dump قابل‌انتقال.

Dump یک آرشیو چندفایلی، خوداعتبارسنج‌پذیر از خروجی کامل Word Factory
برای یک فایل است:

    <dump-dir>/
      dump-manifest.json    ← این ماژول (قرارداد d-1)
      manifest.json         ← مانیفست اجرای WF (m-2)
      document.json         ← مدل سند (متادیتا/ساختار/شناسه‌ها)
      blocks.jsonl          ← هر خط = یک بلوک (RAW + NORMALIZED + content_hash)
      quality-report.json   ← ۸ check + score + status (Quality Gate)
      report.md             ← گزارش انسانی

قواعد طراحی (PCM-14C.3، مبتنی بر ممیزی PCM-14C.1/2 — مسیر A):
- Dump تابع خالص و **فقط‌خوانده** از دایرکتوری خروجی WF است: بدون
  parse مجدد، بدون LLM، بدون ES، بدون DB، بدون شبکه.
- RAW بایت‌به‌بایت حفظ می‌شود؛ NORMALIZED دقیقاً همان چیزی است که
  سیاست **ثبت‌شده** در manifest تولید کرده → با بازسازی policy از
  dump-manifest قابل بازرسی مجدد است (بدون ES).
- determinism: اجرای دوباره‌ی generate_dump روی همان خروجی WF →
  آرشیو بایت‌به‌بایت یکسان (تنها استثنا: `generated_at`)؛ regenerate
  روی همان دایرکتوری، فایل‌ها را **جای‌جای** بازنویسی می‌کند (بدون
  خروجی تکراری).
- سازگاری به‌پایین: اجرای WF با مانیفست m-1 یا m-2 پذیرفته می‌شود؛
  در m-1 سیاست ثبت نشده → `normalizer_policy: null` + بازرسی
  بازنرمال‌سازی skipped با warning صریح.
- ترتیب قطعی فایل‌ها در `files[]` همان ترتیب CANONICAL_FILES است؛
  ترتیب بلوک‌ها = `block_index` پیوسته از 0 (ترتیب واقعی body).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil

from .errors import FactoryError
from .models import FACTORY_VERSION, content_hash, utc_now_iso
from .normalize import NormalizationPolicy, PersianNormalizer

DUMP_VERSION = "d-1"

#: ترتیب قطعی و مستند فایل‌های WF داخل Dump
CANONICAL_FILES = (
    "manifest.json",
    "document.json",
    "blocks.jsonl",
    "quality-report.json",
    "report.md",
)

#: کلیدهای الزامی هر خط blocks.jsonl (قرارداد بلوک WF)
BLOCK_REQUIRED_KEYS = (
    "block_id", "block_index", "type", "raw_text",
    "normalized_text", "norm_version", "content_hash", "page",
)

#: بلوک‌هایی که در service normalized = raw قرار می‌گیرد
_NON_NORMALIZED_TYPES = ("empty", "pagebreak", "table")


class DumpError(FactoryError):
    """خروجی WF نامعتبر برای ساخت Dump، یا ورودی/مغایرت یکپارچگی."""

    code = "dump_error"


def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _file_format(name: str) -> str:
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith(".md"):
        return "markdown"
    return "json"


# ---------------------------------------------------------------------------
# تولید Dump
# ---------------------------------------------------------------------------

def generate_dump(wf_dir: str, dump_dir: str,
                  source_docx: str | None = None) -> dict:
    """ساخت Dump از خروجی یک اجرای Word Factory (فقط‌خوانده).

    wf_dir: دایرکتوری خروجی WF (حاوی 5 فایل + manifest.json)
    dump_dir: مقصد Dump (ساخت/بازنویسی درجا — idempotent)
    source_docx: (اختیاری) فایل docx اصلی — اگر داده شد، SHA-256 آن
        با `file.sha256` مانیفست WF مقایسه می‌شود (mismatch → DumpError).

    برگشت: dict همان dump-manifest.json
    """
    wf_dir = os.path.abspath(wf_dir)
    manifest_path = os.path.join(wf_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise DumpError(
            f"manifest.json در {wf_dir} پیدا نشد — آیا مسیر خروجی WF را دادید؟",
            path=manifest_path)
    m = _load_json(manifest_path)
    mv = m.get("manifest_version")
    if mv not in ("m-1", "m-2"):
        raise DumpError(
            f"نسخه مانیفست WF نامشخص: {mv!r} (فقط m-1/m-2)", version=mv)

    fileinfo = m.get("file") or {}
    input_sha = fileinfo.get("sha256")
    if not input_sha:
        raise DumpError("manifest.file.sha256 غایب — اجرای WF ناقص است")

    # وجود و پُریِ هر 5 فایل WF
    for name in CANONICAL_FILES:
        p = os.path.join(wf_dir, name)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            raise DumpError(f"فایل WF ناموجود یا خالی: {name}", path=p)

    # یکپارچگی داخلی مانیفست WF: hash هر خروجی باید با فایل واقعی بپیوندد
    for out_name, info in (m.get("outputs") or {}).items():
        p = os.path.join(wf_dir, os.path.basename(info.get("path", "")))
        if not os.path.isfile(p):
            raise DumpError(f"خروجی WF در outputs غایب: {out_name}")
        real = _sha256(p)
        if real != info.get("sha256"):
            raise DumpError(
                f"hash خروجی WF با مانیفست نمی‌خواند: {out_name}",
                expected=info.get("sha256"), actual=real)

    # SHA ورودی: بازخوردگیری فقط در صورت دادن فایل اصلی
    input_sha_source = "manifest"
    if source_docx:
        if not os.path.isfile(source_docx):
            raise DumpError(f"فایل ورودی پیدا نشد: {source_docx}")
        h = _sha256(source_docx)
        if h != input_sha:
            raise DumpError(
                "SHA-256 فایل ورودی با مانیفست WF نمی‌خواند — جفت‌شدگی غلط",
                expected=input_sha, actual=h)
        input_sha_source = "rehashed"

    # شمارش بلوک‌ها (شمارندهٔ واقعی — بازخوانی JSONL)
    blocks_path = os.path.join(wf_dir, "blocks.jsonl")
    with open(blocks_path, encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    for i, line in enumerate(lines, 1):
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            raise DumpError(f"blocks.jsonl خط {i}: JSON نامعتبر", error=str(e))
    n_blocks = len(lines)
    counts = m.get("counts") or {}
    if counts.get("blocks") is not None and counts["blocks"] != n_blocks:
        raise DumpError(
            "شمار بلوک‌های مانیفست WF با blocks.jsonl نمی‌خواند",
            manifest=counts.get("blocks"), jsonl=n_blocks)

    doc = _load_json(os.path.join(wf_dir, "document.json"))
    meta_fields = (doc.get("metadata") or {}).get("fields") or {}

    def _val(k: str):
        v = meta_fields.get(k) or {}
        return v.get("value")

    # کپی بایت‌به‌بایت + hash/size هر فایل
    os.makedirs(os.path.abspath(dump_dir), exist_ok=True)
    entries = []
    for name in CANONICAL_FILES:
        dst = os.path.join(dump_dir, name)
        shutil.copyfile(os.path.join(wf_dir, name), dst)
        e = {
            "name": name,
            "sha256": _sha256(dst),
            "size_bytes": os.path.getsize(dst),
            "encoding": "utf-8",
            "format": _file_format(name),
        }
        if name == "blocks.jsonl":
            e["line_count"] = n_blocks
        entries.append(e)

    versions = m.get("versions") or {}
    dm = {
        "dump_contract_version": DUMP_VERSION,
        "generated_at": utc_now_iso(),
        "generator": f"word-factory/{FACTORY_VERSION}",
        "source": {
            "kind": "word-factory-run",
            "input_file": {
                "filename": fileinfo.get("filename"),
                "file_id": fileinfo.get("file_id"),
                "size_bytes": fileinfo.get("size_bytes"),
                "sha256": input_sha,
                "sha256_source": input_sha_source,  # manifest | rehashed
            },
        },
        "identifiers": {
            "file_id": fileinfo.get("file_id"),
            "work_id": m.get("work_id"),
            "edition_id": m.get("edition_id"),
            "volume_id": m.get("volume_id"),
        },
        "document": {
            "title": _val("title"),
            "author": _val("author"),
            "publisher": _val("publisher"),
            "publish_year": _val("publish_year"),
            "volume_no": (doc.get("metadata") or {}).get("volume"),
            "language": "fa",
        },
        "versions": {
            "manifest": mv,
            "schema": m.get("schema_version"),
            "parser": versions.get("parser"),
            "normalizer": versions.get("normalizer"),
            "normalizer_policy": versions.get("normalizer_policy"),
            "factory": versions.get("factory"),
        },
        "files": entries,
        "counts": {
            "blocks": n_blocks,
            "total_chars": counts.get("total_chars"),
        },
        "quality": {
            "status": (m.get("processing") or {}).get("status"),
            "score": (m.get("quality") or {}).get("score"),
            "quality_status": (m.get("quality") or {}).get("status"),
        },
        "integrity": {
            "input_sha256": input_sha,
            "blocks_hash": m.get("blocks_hash"),  # m-2؛ در m-1 null
            "file_hashes_verified": True,
        },
    }
    _write_json(os.path.join(dump_dir, "dump-manifest.json"), dm)
    return dm


# ---------------------------------------------------------------------------
# اعتبارسنجی Dump (بدون ES/DB/شبکه — فقط فایل‌های خود Dump)
# ---------------------------------------------------------------------------

def _policy_from_versions(dm: dict):
    """بازسازی NormalizationPolicy از versions ثبت‌شده (None = ثبت نشده)."""
    v = dm.get("versions") or {}
    pol = v.get("normalizer_policy")
    if not isinstance(pol, dict):
        return None
    try:
        return NormalizationPolicy(
            version=pol.get("version", "n-1"),
            nfkc=bool(pol.get("nfkc", False)),
            arabic_to_persian=bool(pol.get("arabic_to_persian", True)),
            zwnj=bool(pol.get("zwnj", True)),
            collapse_spaces=bool(pol.get("collapse_spaces", True)),
            strip_zwsp=bool(pol.get("strip_zwsp", True)),
            strip_rlm=bool(pol.get("strip_rlm", True)),
            digits=pol.get("digits", "keep"),
        )
    except Exception:
        return None


def validate_dump(dump_dir: str) -> tuple[bool, list[str], list[str]]:
    """اعتبارسنجی کامل Dump — برگشت (ok, errors, warnings).

    بررسی‌ها (بدون هیچ وابستگی خارجی):
    V1  dump-manifest.json موجود و قرارداد d-1
    V2  تمام فایل‌های فهرست‌شده موجودند؛ SHA-256 و size هرکدام می‌خواند
    V3  5 فایل WF + dump-manifest همه حاضرند
    V4  blocks.jsonl: هر خط JSON معتبر، کلیدهای قرارداد، index پیوسته از 0،
        block_id یکتا و مطابق `b{index:05d}:{type}`، page=null
    V5  content_hash هر بلوک = sha256(normalized_text)[:16] (بازمحاسبه)
    V6  normalized_text = خروجی policy ثبت‌شده روی raw_text (بازنرمال‌سازی)
    V7  norm_version هر بلوک با versions.normalizer مانیفست می‌خواند
    V8  شمارش: line_count == counts.blocks == شمارش مانیفست WF
    V9  مانیفست WF: نسخه معتبر + hash خروجی‌های آن با فایل‌های Dump می‌خواند
    V10 quality-report.json: status معتبر؛ «done» نباید «failed» باشد
    V11 شناسه‌های document.json با identifiers مانیفست Dump می‌خواند
    """
    errors: list[str] = []
    warnings: list[str] = []
    dump_dir = os.path.abspath(dump_dir)
    dm_path = os.path.join(dump_dir, "dump-manifest.json")
    if not os.path.isfile(dm_path):
        return False, ["dump-manifest.json: not found"], []
    try:
        dm = _load_json(dm_path)
    except (json.JSONDecodeError, OSError) as e:
        return False, [f"dump-manifest.json: unreadable ({e})"], []

    cv = dm.get("dump_contract_version")
    if cv != DUMP_VERSION:
        errors.append(f"unsupported dump contract: {cv!r} (expected {DUMP_VERSION})")

    # V2/V3: فایل‌ها
    seen: set[str] = set()
    for e in dm.get("files") or []:
        name = e.get("name")
        if not name:
            errors.append("dump-manifest: file entry without name")
            continue
        seen.add(name)
        p = os.path.join(dump_dir, name)
        if not os.path.isfile(p):
            errors.append(f"file_missing:{name}")
            continue
        real = _sha256(p)
        if real != e.get("sha256"):
            errors.append(f"sha256_mismatch:{name}")
        if os.path.getsize(p) != e.get("size_bytes"):
            errors.append(f"size_mismatch:{name}")
    missing = [f for f in CANONICAL_FILES if f not in seen]
    if missing:
        errors.append("dump-manifest_missing_entries:" + ",".join(missing))

    versions = dm.get("versions") or {}
    norm_version = versions.get("normalizer")
    policy = _policy_from_versions(dm)
    if policy is None:
        warnings.append(
            "normalizer_policy not recorded (m-1 run) — re-normalization check skipped")

    # V4..V8: blocks.jsonl
    bp = os.path.join(dump_dir, "blocks.jsonl")
    if os.path.isfile(bp):
        with open(bp, encoding="utf-8") as f:
            raw_lines = [l for l in f.read().splitlines() if l.strip()]
        ids: set[str] = set()
        for i, line in enumerate(raw_lines):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"invalid_jsonl_line:{i + 1}")
                continue
            for k in BLOCK_REQUIRED_KEYS:
                if k not in rec:
                    errors.append(f"missing_key:{k}@line{i + 1}")
            bid = rec.get("block_id")
            if rec.get("block_index") != i:
                errors.append(f"block_order: line {i + 1} index={rec.get('block_index')}")
            if bid is not None:
                if bid in ids:
                    errors.append(f"dup_block_id:{bid}")
                if bid != f"b{i:05d}:{rec.get('type')}":
                    errors.append(f"block_id_mismatch:{bid} (line {i + 1})")
                ids.add(bid)
            if rec.get("page") is not None:
                errors.append(f"page_not_null:{bid}")
            if rec.get("content_hash") != content_hash(rec.get("normalized_text", "")):
                errors.append(f"content_hash_mismatch:{bid}")
            if rec.get("norm_version") != norm_version:
                errors.append(f"norm_version_mismatch:{bid}")
            # V6: بازنرمال‌سازی با policy ثبت‌شده
            if policy is not None:
                raw_t = rec.get("raw_text", "")
                if rec.get("type") in _NON_NORMALIZED_TYPES:
                    expected = raw_t
                else:
                    expected, _ = PersianNormalizer(policy).normalize(raw_t)
                if expected != rec.get("normalized_text"):
                    errors.append(f"normalized_mismatch:{bid}")
        lc = next((e.get("line_count") for e in dm.get("files") or []
                   if e.get("name") == "blocks.jsonl"), None)
        if lc is not None and lc != len(raw_lines):
            errors.append(f"line_count_mismatch:{lc}!={len(raw_lines)}")
        cb = (dm.get("counts") or {}).get("blocks")
        if cb is not None and cb != len(raw_lines):
            errors.append(f"counts_blocks_mismatch:{cb}!={len(raw_lines)}")
        if not raw_lines:
            warnings.append("dump contains zero blocks (empty document?)")
    else:
        errors.append("file_missing:blocks.jsonl")

    # V9: مانیفست WF
    mp = os.path.join(dump_dir, "manifest.json")
    wf_sha_by_file = {e["name"]: e.get("sha256") for e in dm.get("files") or []}
    if os.path.isfile(mp):
        try:
            m = _load_json(mp)
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"manifest.json: unreadable ({e})")
        else:
            if m.get("manifest_version") not in ("m-1", "m-2"):
                errors.append(f"wf_manifest_version_unsupported:{m.get('manifest_version')}")
            out_to_file = {"blocks": "blocks.jsonl", "document": "document.json",
                           "quality_report": "quality-report.json",
                           "report_md": "report.md"}
            for out_name, info in (m.get("outputs") or {}).items():
                fname = out_to_file.get(out_name)
                if fname and info.get("sha256") != wf_sha_by_file.get(fname):
                    errors.append(f"wf_output_hash_mismatch:{out_name}")
    # V10: quality
    qp = os.path.join(dump_dir, "quality-report.json")
    if os.path.isfile(qp):
        try:
            q = _load_json(qp)
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"quality-report.json: unreadable ({e})")
        else:
            q_status = q.get("status")
            if q_status not in ("ok", "manual_review", "failed"):
                errors.append(f"quality_status_unknown:{q_status}")
            run_status = (dm.get("quality") or {}).get("status")
            if run_status == "done" and q_status == "failed":
                errors.append("quality_gate:run_done_but_quality_failed")
    # V11: identities
    dp = os.path.join(dump_dir, "document.json")
    if os.path.isfile(dp):
        try:
            d = _load_json(dp)
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"document.json: unreadable ({e})")
        else:
            ident = dm.get("identifiers") or {}
            if d.get("work_id") != ident.get("work_id"):
                errors.append(f"work_id_mismatch:{d.get('work_id')}!={ident.get('work_id')}")
            if d.get("edition_id") != ident.get("edition_id"):
                errors.append("edition_id_mismatch")

    return (not errors), errors, warnings


def dump_summary(dump_dir: str) -> dict:
    """خلاصهٔ Manifest + وضعیت یکپارچگی (برای نمایش/automation)."""
    ok, errors, warnings = validate_dump(dump_dir)
    summary = {"valid": ok, "errors": errors, "warnings": warnings}
    dm_path = os.path.join(os.path.abspath(dump_dir), "dump-manifest.json")
    if os.path.isfile(dm_path):
        try:
            dm = _load_json(dm_path)
            summary.update({
                "contract": dm.get("dump_contract_version"),
                "generator": dm.get("generator"),
                "identifiers": dm.get("identifiers"),
                "document": dm.get("document"),
                "versions": dm.get("versions"),
                "counts": dm.get("counts"),
                "quality": dm.get("quality"),
                "integrity": dm.get("integrity"),
            })
        except (json.JSONDecodeError, OSError):
            pass
    return summary

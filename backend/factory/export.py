"""factory.export — JsonlExporter + ProcessingManifest + گزارش انسانی.

خروجی‌های هر فایل (در out_dir/):
  manifest.json          — فهرست خروجی‌ها + hash + نسخه‌ها + run info
  document.json          — metadata + structure + file info
  blocks.jsonl           — هر خط = یک بلوک (raw + normalized + قرارداد)
  quality-report.json    — QualityReport.to_dict()
  report.md              — گزارش انسانی فارسی
"""
from __future__ import annotations

import json
import os
import time

from .models import (FACTORY_VERSION, MANIFEST_VERSION, NORM_VERSION,
                     PARSER_VERSION, SCHEMA_VERSION, ProcessedDocument,
                     utc_now_iso)


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


class ProcessingManifest:
    """manifest.json — نسخه‌شده و deterministic (به‌جز timestamps)."""

    def build(self, doc: ProcessedDocument, out_paths: dict[str, str],
              run_status: str, run_error: str | None = None) -> dict:
        m = {
            "manifest_version": MANIFEST_VERSION,
            "schema_version": SCHEMA_VERSION,
            "file": doc.file.to_dict(),
            "work_id": doc.work_id,
            "edition_id": doc.edition_id,
            "volume_id": doc.volume_id,
            "versions": {
                "parser": doc.parser_version,
                "normalizer": doc.norm_version,
                # PCM-14C.3: سیاست کامل نرمال‌سازی (نه فقط نسخه) — رفع
                # ابهام ممیزی PCM-14C.2 §1.6 (دو اجرای متفاوتِ همان فایل).
                "normalizer_policy": doc.normalizer_policy,
                "factory": FACTORY_VERSION,
            },
            # hash مجموع بلوک‌ها (idempotency WF-10 — بدون بازخوانی JSONL)
            "blocks_hash": doc.blocks_hash(),
            "processing": {
                "status": run_status,
                "error": run_error,
                "started_at": doc.started_at,
                "finished_at": doc.finished_at,
                "duration_ms": doc.duration_ms,
            },
            "outputs": {
                name: {"path": path, "sha256": _sha256(path)}
                for name, path in out_paths.items()
            },
            "counts": {
                "blocks": len(doc.blocks),
                "total_chars": doc.total_chars,
            },
            "quality": {"score": doc.quality.score, "status": doc.quality.status},
        }
        return m


def _sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class JsonlExporter:
    def __init__(self, out_dir: str):
        self.out_dir = os.path.abspath(out_dir)
        os.makedirs(self.out_dir, exist_ok=True)

    def export(self, doc: ProcessedDocument, run_status: str,
               run_error: str | None = None) -> dict[str, str]:
        # 1) blocks.jsonl
        blocks_path = os.path.join(self.out_dir, "blocks.jsonl")
        _write_jsonl(blocks_path, [b.unified_record() for b in doc.blocks])

        # 2) document.json
        doc_path = os.path.join(self.out_dir, "document.json")
        _write_json(doc_path, {
            "schema_version": SCHEMA_VERSION,
            "file": doc.file.to_dict(),
            "work_id": doc.work_id,
            "edition_id": doc.edition_id,
            "volume_id": doc.volume_id,
            "parser_version": doc.parser_version,
            "norm_version": doc.norm_version,
            "metadata": doc.metadata.to_dict(),
            "structure": doc.structure.to_dict(),
            "blocks": [
                {"block_id": b.block_id, "block_index": b.block_index,
                 "type": b.type, "style": b.style,
                 "heading_level": b.heading_level,
                 "parent_block_id": b.parent_block_id,
                 "position": b.block_index,
                 "source_ref": b.source_ref or None,
                 "page": None,
                 "processing_status": "ok",
                 "quality_status": "ok" if not b.warnings else "warn"}
                for b in doc.blocks
            ],
        })

        # 3) quality-report.json
        quality_path = os.path.join(self.out_dir, "quality-report.json")
        _write_json(quality_path, doc.quality.to_dict())

        # 4) report.md
        md_path = os.path.join(self.out_dir, "report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self._markdown(doc))

        # 5) manifest.json (آخر — چون hash خروجی‌های دیگر را دارد)
        out_paths = {
            "blocks": blocks_path,
            "document": doc_path,
            "quality_report": quality_path,
            "report_md": md_path,
        }
        manifest = ProcessingManifest().build(doc, out_paths, run_status, run_error)
        manifest_path = os.path.join(self.out_dir, "manifest.json")
        _write_json(manifest_path, manifest)
        out_paths["manifest"] = manifest_path
        return out_paths

    @staticmethod
    def _markdown(doc: ProcessedDocument) -> str:
        q = doc.quality
        lines = [
            "# گزارش پردازش Word Factory (V0.1)",
            "",
            f"- **فایل:** `{doc.file.filename}`",
            f"- **file_id:** `{doc.file.file_id}`",
            f"- **SHA-256:** `{doc.file.sha256}`",
            f"- **حجم:** {doc.file.size_bytes:,} بایت",
            f"- **فرمت:** {doc.file.format} ({doc.file.detected_by})",
            f"- **parser:** {doc.parser_version} · **normalizer:** {doc.norm_version}",
            f"- **بلوک‌ها:** {len(doc.blocks)} · **کاراکترها:** {doc.total_chars:,}",
            f"- **نتیجه کیفیت:** **{q.status}** (score={q.score})",
            "",
            "## کیفیت",
            "",
            "| check | نتیجه |",
            "|---|:---:|",
        ]
        for c in q.checks:
            lines.append(f"| {c['name']} | {'✅' if c['ok'] else '❌'} {c['detail']} |")
        lines += ["", "## ساختار", ""]
        lines.append(f"- تیترها: {len(doc.structure.headings)} · فصل‌ها (H1): {len(doc.structure.chapters)}")
        lines.append(f"- front matter: {doc.structure.front_matter_blocks} بلوک")
        for note in doc.structure.notes:
            lines.append(f"- یادداشت: {note}")
        lines += ["", "## کتاب‌شناسی (extract-only)", ""]
        for k, v in doc.metadata.fields.items():
            d = v.to_dict()
            val = d["value"] if d["value"] is not None else "— (غایب)"
            lines.append(f"- **{k}:** {val} _(منبع: {d['source_ref']}, confidence {d['confidence']:.1f})_")
        if doc.metadata.volume_no:
            lines.append(f"- **جلد:** {doc.metadata.volume_no} ({doc.metadata.volume_source})")
        lines += ["", "## موارد استخراج‌نشده", ""]
        if q.unextracted["losses"]:
            for k, v in q.unextracted["losses"].items():
                lines.append(f"- {k}: {v}")
        else:
            lines.append("- (هیچ ساختاری گم نشده)")
        if q.unextracted.get("footnotes_extracted"):
            lines.append(f"- پاورقی‌های استخراج‌شده: {q.unextracted['footnotes_extracted']}")
        if q.unextracted.get("endnotes_extracted"):
            lines.append(f"- Endnoteهای استخراج‌شده: {q.unextracted['endnotes_extracted']}")
        lines += ["", "## نمونه بلوک‌ها (اولین ۵)", ""]
        for b in doc.blocks[:5]:
            preview = (b.raw_text[:80] + "…") if len(b.raw_text) > 80 else (b.raw_text or "(جدول: %d سطر)" % (len(b.table_rows or [])))
            lines.append(f"- `{b.block_id}` [{b.type}] {preview}")
        lines += ["", "---", f"_تولیدشده {utc_now_iso()} — Word Factory V0.1_"]
        return "\n".join(lines)

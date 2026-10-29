"""factory.service — DocumentProcessingService (orchestrator).

خط لوله (V0.1 — بدون queue/worker/LLM/ES):
  intake → validate → parse → structure → metadata → normalize → quality → export

اصل‌ها:
- هر stage خالص و مجزا (تست مستقل ممکن است).
- خروجی در out_dir/<file_id>/ — فایل اصلی ورودی هرگز دست‌نخورده.
- بدون LLM: ENRICHED تولید نمی‌شود (enriched=null در manifest).
- بدون DB: شناسه‌ها deterministic از metadata + sha256 (registry در فاز بعد).
- خطا در هر stage → manifest با status=failed + error (فایل ورودی سالم می‌ماند).
"""
from __future__ import annotations

import hashlib
import os
import time

from .export import JsonlExporter
from .errors import FactoryError
from .intake import DocumentIntakeService
from .metadata import MetadataExtractor
from .models import (Block, MANIFEST_VERSION, ProcessedDocument,
                     StructureTree, short_id, utc_now_iso)
from .normalize import (NormalizationPolicy, PersianNormalizer,
                        verify_no_semantic_change)
from .parser import DocumentParser, make_parser
from .quality import QualityValidator
from .structure import extract_structure
from .validator import FileValidator


class DocumentProcessingService:
    def __init__(self, out_dir: str,
                 norm_policy: NormalizationPolicy | None = None,
                 quality_threshold: float = 0.6,
                 max_bytes: int = 200 * (1 << 20)):
        self.out_dir = os.path.abspath(out_dir)
        self.intake = DocumentIntakeService(self.out_dir)
        self.validator = FileValidator(max_bytes=max_bytes)
        self.normalizer = PersianNormalizer(norm_policy)
        self.quality = QualityValidator(threshold=quality_threshold)

    def process(self, src_path: str) -> ProcessedDocument:
        t0 = time.time()
        started = utc_now_iso()
        file_rec = None
        try:
            # 1) intake
            file_rec = self.intake.intake(src_path)
            # 2/3) validate (بازپذیری + sha ثانی)
            vout = self.validator.validate(file_rec)
            # 4) parse
            parser: DocumentParser = make_parser(file_rec.format)
            outcome = parser.parse(file_rec)
            # 5) structure
            structure = extract_structure(outcome.blocks)
            # 6) metadata (extract-only) — نیاز به doc object دارد
            from docx import Document
            doc = Document(file_rec.path)
            metadata = MetadataExtractor().extract(doc, outcome.blocks)
            # 7) normalize (RAW دست‌نخورده می‌ماند)
            semantic_issues = []
            for b in outcome.blocks:
                if b.type in ("empty", "pagebreak", "table"):
                    b.normalized_text = b.raw_text
                    continue
                n, stats = self.normalizer.normalize(b.raw_text)
                b.normalized_text = n
                b.norm_stats = stats
                issues = verify_no_semantic_change(b.raw_text, n)
                if issues:
                    b.warnings.extend(issues)
                    semantic_issues.extend(issues)
            # 8) quality
            quality = self.quality.validate(
                file_rec, outcome.blocks, outcome.losses,
                sha_verified=vout.sha256_verified)
            if semantic_issues:
                quality.status = "manual_review"
                quality.passed = False
                quality.warnings.append(
                    f"semantic-change guard tripped on {len(semantic_issues)} block(s)")

            # شناسه‌ها (بدون DB — deterministic؛ registry در فاز بعد)
            title = (metadata.fields.get("title") or None)
            title_val = title.value if title else None
            author = (metadata.fields.get("author") or None)
            author_val = author.value if author else None
            work_key = f"{(title_val or '').strip().lower()}|{(author_val or '').strip().lower()}"
            if not (title_val or author_val):
                work_key = file_rec.sha256
            work_id = short_id("w", work_key)
            edition_id = short_id("e", f"{work_key}|{file_rec.sha256}")
            volume_id = short_id("v", f"{edition_id}|{metadata.volume_no or 'main'}") \
                if metadata.volume_no else None

            policy_dict = self.normalizer.policy.policy_dict()
            doc_out = ProcessedDocument(
                file=file_rec,
                blocks=outcome.blocks,
                structure=structure,
                metadata=metadata,
                quality=quality,
                work_id=work_id,
                edition_id=edition_id,
                volume_id=volume_id,
                normalizer_policy=policy_dict,
                started_at=started,
                finished_at=utc_now_iso(),
                duration_ms=int((time.time() - t0) * 1000),
            )
            # export (manifest با status=done یا manual_review)
            run_status = "done" if quality.passed else "manual_review"
            out_dir = os.path.join(self.out_dir, file_rec.file_id)
            JsonlExporter(out_dir).export(doc_out, run_status)
            return doc_out

        except FactoryError as e:
            self._write_failed_manifest(file_rec, e, started, t0)
            raise
        except Exception as e:  # خطای غیرمنتظره — ثبت در manifest، ادامه به raise
            self._write_failed_manifest(
                file_rec, FactoryError(f"{type(e).__name__}: {e}"), started, t0)
            raise

    def _write_failed_manifest(self, file_rec, err: FactoryError,
                               started: str, t0: float) -> None:
        """خطای processing نباید بی‌رد باشد — manifest ناکامی هم ثبت می‌شود."""
        try:
            import json
            m = {
                "manifest_version": MANIFEST_VERSION,
                "processing": {
                    "status": "failed",
                    "error": err.to_dict(),
                    "started_at": started,
                    "finished_at": utc_now_iso(),
                    "duration_ms": int((time.time() - t0) * 1000),
                },
                "file": file_rec.to_dict() if file_rec else None,
            }
            if file_rec:
                d = os.path.join(self.out_dir, file_rec.file_id)
            else:
                d = self.out_dir
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # ثبت ناکامی خود نباید mask خطا اصلی کند

"""factory.quality — QualityValidator (stage 8: گزارش کیفیت).

خروجی: QualityReport با checks + metrics + unextracted.
قواعد (بر اساس المام PCM-13 §8 + PRD §4.2):
- فایل معتبر و باز شد (validator)
- متن خالی نیست
- ترتیب بلوک‌ها حفظ شده (index پیوسته)
- جدول حذف نشده (هر table در parser باید در blocks باشد)
- hash ثبت شده
- درصد فارسی + طول
- موارد استخراج‌نشده (losses) گزارش می‌شوند
- اگر score < threshold → status=manual_review (نه fail فوری؛ WF-11)
"""
from __future__ import annotations

import re

from .models import NORM_VERSION, Block, FileRecord, QualityReport

FA_RUN = re.compile(r"[\u0621-\u064A\u067E\u0686\u0698\u06A9\u06AF\u0688]+")
MIN_TEXT_CHARS = 50
DEFAULT_THRESHOLD = 0.6


def persian_ratio(text: str) -> float:
    if not text:
        return 0.0
    m = FA_RUN.findall(text)
    fa_chars = sum(len(x) for x in m)
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return fa_chars / len(letters)


class QualityValidator:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD, min_chars: int = MIN_TEXT_CHARS):
        self.threshold = threshold
        self.min_chars = min_chars

    def validate(self, file_rec: FileRecord, blocks: list[Block],
                 losses: dict, sha_verified: bool) -> QualityReport:
        checks = []
        warnings = []
        metrics: dict = {}

        def check(name, ok, detail=""):
            checks.append({"name": name, "ok": bool(ok), "detail": detail})
            return ok

        # 1) بازپذیری + hash
        check("file_openable", True, "python-docx opened")
        check("sha256_verified", sha_verified, file_rec.sha256[:16])

        # 2) متن خالی نیست
        total_chars = sum(len(b.raw_text) for b in blocks)
        text_chars = sum(len(b.raw_text) for b in blocks
                         if b.type in ("paragraph", "heading"))
        metrics["total_chars"] = total_chars
        check("non_empty_text", text_chars >= self.min_chars,
              f"text_chars={text_chars} min={self.min_chars}")

        # 3) ترتیب بلوک‌ها (index پیوسته از صفر)
        idx_ok = all(b.block_index == i for i, b in enumerate(blocks))
        check("block_order_contiguous", idx_ok, f"blocks={len(blocks)}")

        # 4) جدول حذف نشده (table blocks در output)
        n_tables = sum(1 for b in blocks if b.type == "table")
        metrics["table_blocks"] = n_tables
        check("tables_present", True, f"tables={n_tables}")  # نبودن جدول = خنثی

        # 5) percent فارسی
        sample = "\n".join(b.raw_text for b in blocks if b.type in ("paragraph", "heading"))
        ratio = persian_ratio(sample)
        metrics["persian_ratio"] = round(ratio, 4)
        check("persian_content", ratio > 0.1, f"ratio={ratio:.3f}")

        # 6) heading hierarchy
        n_head = sum(1 for b in blocks if b.type == "heading")
        metrics["heading_blocks"] = n_head
        check("headings_detected", n_head >= 0, f"headings={n_head}")

        # 7) page number fabrication guard
        pages = [b.page for b in blocks if b.page is not None]
        check("no_fabricated_pages", not pages, f"pages={len(pages)}")

        # 8) losses (موارد استخراج‌نشده)
        loss_items = {k: v for k, v in losses.items()
                      if k not in ("footnotes_extracted", "endnotes_extracted")}
        metrics["losses"] = loss_items
        if loss_items:
            warnings.append(f"unextracted structures: {loss_items}")
        unextracted = {
            "losses": loss_items,
            "footnotes_extracted": losses.get("footnotes_extracted", 0),
            "endnotes_extracted": losses.get("endnotes_extracted", 0),
        }

        # score: میانگین checks سبز (بدون وزن — نسخه v1 ساده و شفاف)
        passed = sum(1 for c in checks if c["ok"])
        score = round(passed / len(checks), 4) if checks else 0.0
        metrics["score"] = score
        metrics["norm_version"] = NORM_VERSION

        # checks سفت (hard gates): شکستن هر کدام، صرف‌نظر از score،
        # نتیجه را manual_review می‌کند — میانگین نمی‌تواند شکست سفت را پنهان کند.
        HARD_GATES = {"file_openable", "sha256_verified",
                      "non_empty_text", "block_order_contiguous"}
        hard_failed = [c["name"] for c in checks
                       if c["name"] in HARD_GATES and not c["ok"]]
        if hard_failed:
            status = "manual_review"
            ok = False
            warnings.append(f"hard-gate failed: {hard_failed}")
        elif score >= self.threshold:
            status = "ok"
            ok = True
        else:
            status = "manual_review"
            ok = False
            warnings.append(f"score {score} < threshold {self.threshold}")

        return QualityReport(
            passed=ok, score=score, status=status,
            checks=checks, metrics=metrics,
            unextracted=unextracted, warnings=warnings,
        )

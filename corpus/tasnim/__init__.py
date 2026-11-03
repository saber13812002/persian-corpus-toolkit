# -*- coding: utf-8 -*-
"""corpus.tasnim — PCM-20.3: Tasnim Corpus Factory & Dataset Versioning.

خط تولید استاندارد، تکرارپذیر و نسخه‌پذیر برای تبدیل خروجی کراول
«تفسیر تسنیم همتا» (PCM-20) به:
  1. پیکره‌ی رسمی (Canonical Corpus) — Work → Edition → Volume → Page
  2. دیتاست‌های نسخه‌پذیر (1/10/50/90/100٪ + تک‌جلد)
  3. خروجی سازگار با ai-dump-builder (adapter — بدون embedding/Neo4j در این فاز)

قواعد سخت:
  * فقط‌خواندن روی ورودی‌ها؛ هیچ حذفی بدون دلیل ثبت‌شده؛ RAW/NORMALIZED جدا.
  * قطعی بودن: همان ورودی + همان پیکربندی → همان خروجی و همان SHA.
  * نسخه‌ها هرگز بازنویسی نمی‌شوند؛ زنجیره‌ی manifest (provenance) در هر نسخه.

استفاده:
    python -m corpus.tasnim.cli --help
"""

__version__ = "1.0.0"

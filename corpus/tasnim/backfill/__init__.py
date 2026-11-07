# -*- coding: utf-8 -*-
"""tasnim.backfill — خط لوله‌ی Backfill صفحات مفقود (PCM-20.6.3).

ماژول‌ها:
    gap          — گزارش شکاف v0004 از pages.jsonl (بازحساب 6 بازه‌ی مفقود)
    fetch_plan   — برنامه‌ی مرتب Fetch + نرخ/بودجه‌ی درخواست (بدون شبکه)
    parse        — ساخت رکورد + پارس barg اصلاح‌شده + volume-candidates
                   (با flag ابهام) + تشخیص تکرار/تغییر محتوا
    checkpoint   — store checkpoint/resume (JSON، idempotent، حفظ stage)
    manifest     — manifest `backfill` + diff نسبت به base + registry + rollback
    runner       — اجرای pipeline (fetch stub با transport تزریق‌شونده)
    cli          — CLI: gap-report | plan | run [--dry-run] | verify | register

قواعد:
    * v0003 (و هر base دیگر) **immutable** است؛ خروجی Backfill فقط افزوده
      می‌شود (append-only) و به نسخه‌ی جدید پیکره (v0004) تبدیل می‌گردد.
    * در این subtask **هیچ درخواست زنده‌ای** وجود ندارد؛ transport واقعی
      فقط با `--allow-live` **و** `BACKFILL_APPROVED=approved` فعال می‌شود.
    * `item_index` کلید مرتب‌سازی است؛ `page_id` کلید یکتایی پیکره است؛
      `barg` شماره‌ی برگ چاپی است (نه کلید) و فقط با parser اصلاح‌شده
      (`parse_barg_all_runs`) تفسیر می‌شود.
    * نسبت‌دادن به جلد هرگز «تخمین» نیست: همه‌ی شواهد (section در URL،
      همسایه‌های موجود) ثبت می‌شوند و ابهام با flag مشخص علامت می‌خورد.
"""

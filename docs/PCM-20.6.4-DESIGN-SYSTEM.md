# PCM-20.6.4 — Design System: Tasnim Web V1

> **مأموریت:** PCM-20.6.4 Track B — سیستم طراحی «کتاب‌خانهٔ دیجیتال تسنیم» (دامنه‌ی هدف: `tasnim.ai.ismc.ir`).
> **وضعیت:** SPEC (فقط طراحی؛ پیاده‌سازی در فاز ۳). تاریخ: 2026-11-07 (Asia/Tehran).
> **منبع تولید اولیه:** skill `ui-ux-pro-max` → فایل پایدار `design-system/tasnim-web/MASTER.md` (پرس‌و‌جواب نهایی: `book reading editorial minimal warm`، دایال‌ها Variance 4 / Motion 3 / Density 5؛ پژوهش تکمیلی: [`docs/pcm-20.6.4-design-research.md`](pcm-20.6.4-design-research.md)).
> **قاعدهٔ این سند:** هر جا مقدار MASTER.md برای زبان فارسی/RTL نامناسب است، این سند **override** می‌کند و دلیلش ثبت می‌شود (§۱.۲). MASTER.md منبع machine-generated است؛ این سند منبع انسانی و معتبرِ فاز ۳ است.

---

## ۱. زبان طراحی (Design Language)

### ۱.۱ هویت بصری

حس بصری هدف: **کتاب‌خانه‌ای علمیِ معتبرِ علوم اسلامی + پلتفرم مدرنِ خواندن**. کاغذ گرم، مرکب تیره، یک لهجه‌ی (accent) علمیِ محدود، شبکه‌بندی منظمِ Swiss-Modernist، حرکتِ پنهان. صریحاً **نه** داشبورد مدیریتی، **نه** JSON viewer، **نه** لندینگ مارکتینگ.

| اصل | تعریف |
|---|---|
| Content-first | متن صفحه در مرکز؛ کروم (nav/footer) کم‌رنگ و کم‌حجم |
| Warm paper | پس‌زمینهٔ کاغذی گرم؛ کارت‌ها کمی روشن‌تر/تیره‌تر از زمینه، هرگز سفید خالصِ تیز |
| One scholarly accent | فقط دو لهجه: amber عمیق (برگ/رابطه‌ی با کتاب) و teal (متادیتا/دانش‌ورزی)؛ رنگ‌های دیگر فقط semantic |
| Grid discipline | گرید ۱۲ ستونه برای چیدمان‌ها؛ ستون خواندن مستقل (prose measure) |
| Subtle motion | فقط fade/shift ≤16px، 150–300ms، با احترام کامل به `prefers-reduced-motion` |
| Honesty | همهٔ کمبودهای داده (صفحه‌های گم‌شده، قطع‌شده‌ها، سوره‌ی «در حال تکمیل») با کامپونیت‌های صریح نشان داده می‌شوند — نه با داده‌ی ساختگی |

### ۱.۲ جدول overrideها نسبت به MASTER.md

| مورد | MASTER.md | این سند | دلیل |
|---|---|---|---|
| Heading/Body font | Cormorant Garamond / Crimson Pro | **Vazirmatn / Noto Naskh Arabic (+ Amiri اختیاری)** | فونت‌های MASTER حروف‌نگاری فارسی ندارند؛ تولید محتوا فارسی است |
| Background | `#FFFBEB` (amber-50) | **`#FAF7F2`** (warm paper خنثی‌تر) | مأموریت صریحاً «warm paper #FAF7F2-ish» خواسته؛ amber-50 بیش‌ازحد زرد است |
| Primary (button) | `#78716C` (stone) | **`#92400E`** (amber-800) | stone روی کاغذ برای دکمه‌ی اصلی ضعیف است؛ amber-800 روی سفید ۸٫۱:۱ (AAA) |
| Accent/CTA | `#D97706` | **`#D97706` فقط decorative**؛ متن/لینک = **`#92400E`** | سفید روی `#D97706` ≈ ۳٫۲:۱ (فقط large/UI ok) — برای متن normal نامعتبر است |
| Muted foreground | `#475569` (slate-600) | **`#57534E`** (stone-600) | هماهنگی گرم با کاغذ (سردی slate حذف)؛ ۵٫۴:۱ روی کاغذ |
| Destructive | `#DC2626` | **`#B91C1C`** (red-700) | ۶٫۶:۱ روی کاغذ (AA)؛ red-600 روی کاغذ ≈ ۴٫۵ حدّی |
| Ring | `#78716C` | **`#0F5C54`** (teal) | focus ring با تمایز از رنگ‌های گرم |
| Page pattern | «Hero + Testimonials + CTA» | **حذف کامل** | این یک کتاب‌خانه است، نه landing مارکتینگ |
| Modal backdrop-filter | `blur(4px)` | **حذف blur** | glassmorphism = anti-pattern مأموریت (B3) |

مقدارهای MASTER.md که بدون تغییر می‌مانند: ساختار tokenها، مقیاس فاصله (8pt)، سطح سایه‌ها، اصل «excessive decoration» به‌عنوان anti-pattern، چک‌لیست pre-delivery.

### ۱.۳ مرجع تولید (provenance)

- `design-system/tasnim-web/MASTER.md` — Category: Book & Reading Tracker؛ Style: Swiss Modernism 2.0؛ Mood: academia, library, parchment, scholarly, prestige؛ dials 4/3/5.
- پرس‌و‌جواب اول (`digital library reading platform editorial content-first academic`) نتایج off-topic داد (پالت خبری قرمز #DC2626 + پترن Hero-Centric) → طبق سیاست retry-once حذف و با `book reading editorial minimal warm` تکرار شد؛ نتیجهٔ دوم حفظ شد (پالت book brown + page amber، mood scholarly).
- تایپوگرافی مستقل (research doc §1) جفت‌فونت editorial-classic (Cormorant Garamond + Libre Baskerville) را تأیید می‌کند که حسّ نیکوست — ولی چون حروف‌نگاری فارسی ندارد، جایگزین فارسی می‌شود و فقط «حسّ serif-classic» آن حفظ می‌شود.
- دیتابیس skill برای RTL خالی بود (research doc §6: 0 نتیجه در html-tailwind) → قواعد RTL از standardهای CSS3 logical properties (§۵) گرفته شده‌اند، نه از دیتابیس.

---

## ۲. توکن‌های رنگ (Color Tokens)

### ۲.۱ پالت روشن (default) — «کاج/کاغذ»

| Token | HEX | کاربرد | کنتراست (WCAG 2.1) | وضعیت |
|---|---|---|---|---|
| `--color-bg` | `#FAF7F2` | پس‌زمینهٔ صفحه | — | override از MASTER |
| `--color-bg-subtle` | `#F3EFE7` | ناحیه‌های فرعی، header/footer, band | — | جدید |
| `--color-surface` | `#FFFFFF` | کارت‌ها، جعبه‌ی ریدر، modal | — | (MASTER `card`) |
| `--color-surface-ink` | `#FBF8F3` | کارت‌های درون‌کاغذی (nested) | — | جدید |
| `--color-text` | `#1C1917` (stone-900) | متن اصلی خواندن | 16.3:1 روی bg / 17.0:1 روی surface | AAA |
| `--color-text-muted` | `#57534E` (stone-600) | متن فرعی، توضیح، meta | 5.4:1 روی bg / 5.9:1 روی surface | AA |
| `--color-text-faint` | `#78716C` (stone-500) | placeholder، caption کوچک (حداقل 14px) | 4.8:1 روی bg / 5.1:1 روی surface | AA |
| `--color-ink` | `#92400E` (amber-800) | **لینک‌ها، دکمهٔ اصلی، عنوان بخش، accent متن** | 7.4:1 روی bg / 8.1:1 روی surface | AAA (normal text) |
| `--color-accent` | `#D97706` (amber-600) | فقط تزئینات بزرگ: خط تکیه (rule)، زینت کاور، progress | 3.2:1 روی bg — **فقط large text / non-text UI (3:1)** | محدود |
| `--color-teal` | `#0F5C54` | متادیتا، badge دانش‌ورزی (SHA، provenance)، focus ring | 6.6:1 روی bg / 7.0:1 روی surface | AAA |
| `--color-teal-soft` | `#E3EFEA` | پس‌زمینهٔ chip متادیتا | — | جدید |
| `--color-border` | `#E5DED2` | مرزهای کاغذی (گرم‌تر از MASTER `#EEEDED`) | — | override |
| `--color-border-strong` | `#C9BFAF` | مرزِ تعاملی، tab active | 2.4:1 (UI 3:1 حدودی — فقط برای مرز غیرحیاتی استفاده می‌شود؛ مرزهای حیاتی با `--color-text-faint`) | قاعدهٔ non-text |
| `--color-danger` | `#B91C1C` (red-700) | خطا، badge quality «قطع/خالی» | 6.6:1 روی bg / 7.0:1 روی surface | AA |
| `--color-danger-soft` | `#FBEAEA` | پس‌زمینهٔ badge خطا | — | جدید |
| `--color-warning` | `#B45309` (amber-700) | وضعیت «در دست بازیابی / truncated» (متن) | 5.3:1 روی bg | AA |
| `--color-warning-soft` | `#FBF0E2` | پس‌زمینهٔ badge هشدار | — | جدید |
| `--color-success` | `#166534` (green-800) | وضعیت کامل/پوشش‌شده | 6.9:1 روی bg | AA |
| `--color-success-soft` | `#E8F1EA` | پس‌زمینهٔ badge موفق | — | جدید |
| `--color-on-primary` | `#FFFFFF` | متن روی دکمهٔ اصلی | 8.1:1 روی `#92400E` | AAA |
| `--color-focus-ring` | `#0F5C54` | focus-visible (4.0:1+ روی همهٔ سطوح) | — | override |

**قواعد ترکیب:**
- متن بر `--color-bg` هرگز زیر 4.5:1؛ متن بزرگ (≥24px یا ≥18.7px bold) زیر 3:1.
- `--color-accent` هرگز برای متن normal استفاده نمی‌شود؛ فقط برای عناصر ≥24px یا non-text.
- رنگ به‌تنهایی حامل معنی نمی‌شود: همهٔ badgeها متن دارند (§۷).

### ۲.۲ پالت تیره (dark reading mode — optional، V1 با flag)

| Token | HEX | کنتراست | وضعیت |
|---|---|---|---|
| `--color-bg` | `#1C1917` | — | |
| `--color-bg-subtle` | `#141210` | — | |
| `--color-surface` | `#292524` | — | |
| `--color-text` | `#E7E5E4` | 13.9:1 روی bg / 12.4:1 روی surface | AAA |
| `--color-text-muted` | `#A8A29E` | 7.5:1 روی bg / 7.0:1 روی surface | AA/AAA |
| `--color-text-faint` | `#8A837B` | 5.3:1 روی bg | AA |
| `--color-ink` (link) | `#FBBF24` (amber-400) | 9.4:1 روی bg | AAA |
| `--color-teal` | `#5EEAD4` — **فقط** برای non-text (ring/border)؛ متن متادیتا = `#A8A29E` | ring: 8.9:1 | |
| `--color-border` | `#413D38` | — | |
| `--color-danger` | `#FCA5A5` | 9.7:1 روی surface | AAA |
| `--color-warning` | `#FCD34D` | 11.0:1 روی surface | AAA |

قاعده: حالت تیره به‌صورت مستقل تست می‌شود (فرض بردن کنتراست روشن ممنوع). سوییچ: دکمهٔ `<button aria-pressed>` در header + احترام به `prefers-color-scheme` در اولین بازدید؛ انتخاب در `localStorage` با key `tasnim-theme`.

### ۲.۳ سایه‌ها (از MASTER.md، بدون تغییر)

| Token | مقدار | کاربرد |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | کارت‌های استراحت |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.10)` | کارت‌های تعاملی (جلد) |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.10)` | drawer, dropdown, popover |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | modal |

در حالت تیره: `--shadow-*` همه صفر (سایه در تیره کارایی بصری ندارد؛ تفکیک با border).

---

## ۳. تایپوگرافی (Persian-capable)

### ۳.۱ جفت‌فونت (فونت‌های MASTER رد شدند — دلیل §۱.۲)

| نقش | فونت | وزن‌ها | جاستیفیکاسیون |
|---|---|---|---|
| **UI / labels / navigation** | **Vazirmatn** (OFL-1.1) | 400, 500, 700 | فارسی + لاتین/اعداد ASCII. متعلّق به خانوادهٔ sans مدرن؛ legibility عالی در چگالی بالا؛ ZWNJ و همتا (hamza)‌ها درست رندر می‌شود |
| **متن خواندنی (reading body)** | **Noto Naskh Arabic** (OFL-1.1) | 400, 500, 700 | حسّ ناسخِ دست‌نویسی؛ خوانایی طولانی بالا؛ پوشش کامل فارسی + عربی (برای آیات) + Latin |
| **Display / عنوان‌های بزرگ (اختیاری)** | **Amiri** (OFL-1.1) | 400, 700 | فقط نام اثر در home و کاورهای SVG؛ حسّ classical manuscript. استفادهٔ محدود (حداکثر ۲ مکان) |
| fallback stack | `Vazirmatn, "Noto Naskh Arabic", Tahoma, system-ui, sans-serif` | | |

- **اعداد:** همهٔ اعداد (item_index, barg, شمارنده‌ها) با **ASCII digits** و `font-variant-numeric: tabular-nums` در جدول‌ها/شمارنده‌ها. اعداد فارسی (۰–۹) فقط داخل متنِ خودِ پیکره (که در source فارسی است) — تبدیل در UI انجام **نمی‌شود** (حفظ fidelity).
- **Self-hosted:** همهٔ فونت‌ها به‌صورت woff2 subset (U+0600–U+06FF + Latin-1 + General Punctuation + U+200C ZWNJ) در `/static/fonts/` سرو می‌شوند — **بستگی به CDN ندارد** (offline-first سازمان). `font-display: swap` + `size-adjust` برای کاهش FOUT.
- **لیسانس:** Vazirmatn — SIL Open Font License 1.1 (repo: googlefonts/vazirmatn). Noto Naskh Arabic — OFL 1.1 (repo: googlefonts/noto-naskh-arabic). Amiri — OFL 1.1 (repo: googlefonts/amiri). همهٔ سه‌گانه اجازهٔ خودسرو‌کردن (self-hosting) را دارند. در footer سایت: «فونت‌ها: Vazirmatn, Noto Naskh Arabic, Amiri — تحت مجوز OFL».

### ۳.۲ مقیاس تایپوگرافی (Naskh-tuned)

| Token | اندازه (desktop / mobile) | line-height | کاربرد |
|---|---|---|---|
| `--text-xs` | 13 / 12px | 1.6 | meta, badge, timestamp |
| `--text-sm` | 15 / 14px | 1.7 | لیست‌ها، breadcrumb, nav |
| `--text-base-ui` | 16 / 15px | 1.6 | فرم‌ها، توضیح، جدول |
| **`--text-reading`** | **19 / 17px** | **2.05 / 1.95** | **متن اصلی صفحه (reader)** |
| `--text-reading-ar` | 21 / 19px | 1.9 | آیات/متون عربی داخل متن (`.ar`، `dir="ltr"` فقط داخل خط، جریان کلی RTL) |
| `--text-h3` | 22 / 20px | 1.5 | عنوان بخش در صفحه |
| `--text-h2` | 28 / 24px | 1.4 | عنوان جلد/مبحث |
| `--text-h1` | 36 / 30px | 1.3 | عنوان صفحه (home: نام اثر با Amiri) |

- **Reading measure (خطِ خواندن):** ستون reader حداکثر **68ch** (محدودهٔ تحقیق skill: 65–75ch)؛ در ≥1280px صفحه reader دو‌ستونه: متن (68ch) + margin meta در inline-start.
- `hyphens: none` (فارسی hyphen ندارد)؛ `overflow-wrap: anywhere` فقط برای کلمات‌بلندِ عربی/لینک.
- **LTR islands:** hash‌ها، URL، page_id، کد JSON همیشه `dir="ltr"` + `unicode-bidi: isolate` + فونت monospace (fallback: `ui-monospace, "Cascadia Mono", Consolas`)؛ فاصلهٔ دو‌طرفه (`margin-inline: 4px`).
- زینت: خط تکیهٔ باریک (1px `--color-accent`) زیر h1 فقط در home — نه در ریدر.

### ۳.۳ فاصله (Spacing — 8pt rhythm، از MASTER density=5)

| Token | مقدار | کاربرد |
|---|---|---|
| `--space-1` | 4px | gap درون chip |
| `--space-2` | 8px | gap آیکون/متن |
| `--space-3` | 12px | padding-inline chip/badge |
| `--space-4` | 16px | padding کم کارت |
| `--space-5` | 24px | padding استاندارد کارت، gap لیست |
| `--space-6` | 32px | gap بخش‌ها |
| `--space-7` | 48px | فاصلهٔ بین‌بخش بزرگ (home) |
| `--space-8` | 64px | padding hero (فقط home) |

Gutter: 16px (mobile) / 24px (≥768) / 40px (≥1280). عرض ماکس محتوا: 1200px (چیدمان)؛ 860px (ریدر).

---

## ۴. Radius / Shadow / Iconography

| Token | مقدار | قاعده |
|---|---|---|
| `--radius-sm` | 6px | chip, badge, input کوچک |
| `--radius-md` | 10px | کارت، دکمه، search box |
| `--radius-lg` | 14px | drawer, modal, cover plate |
| `--radius-full` | 999px | avatar-like (نداریم)، toggle |

**آیکون:** SVG inline فقط، یک خانواده (line-style، stroke 1.75px، 24×24 viewBox). مجموعهٔ حداقلی V1: book, layers (volumes), list (headings), search, chevron (prev/next), info (metadata drawer), alert-triangle (quality), clock (backfill state), sun/moon (theme), menu/close.
- آیکون‌های جهت‌دار (chevron/arrow) در RTL **mirror** می‌شوند: `<use>` با `transform: scaleX(-1)` یا دو asset جدا؛ هرگز `direction` به‌تنهایی به آیکون SVG بسپارید.
- آیکون تزئینی: `aria-hidden="true"`؛ آیکون معنابخش (دکمه‌های icon-only): `aria-label` فارسی + hit area ≥44px.
- **هیچ** آیکون emoji، هیچ آیکون raster (PNG).

---

## ۵. قواعد RTL (مهم‌ترین بخش)

1. `html` → `<html lang="fa" dir="rtl">`.
2. **CSS logical properties صرف:** `margin-inline-start/end`, `padding-inline-*`, `border-inline-start`, `inset-inline-*`, `text-align: start/end`. استفاده از `left/right/float/margin-left` در layout ممنوع (استثنا: فقط برای LTR islands با `direction: ltr`).
3. `scroll-behavior: smooth` فقط وقتی `prefers-reduced-motion: no-preference`.
4. **Mirror کردن:** breadcrumbs، prev/next controls، drawer (از inline-end باز می‌شود)، progress — همه با logical properties خودکار mirror می‌شوند؛ آیکون‌ها دستی (§۴).
5. **LTR stays LTR:** صفحه‌ی reader جریان کلیش RTL است؛ اما آیات/اقتباس‌های عربی داخل `<span dir="ltr" lang="ar">` با `display: inline-block` و `text-align: left` **در همان خط** قرار می‌گیرند (flow خراب نمی‌شود). اعداد داخل متن فارسی: `unicode-bidi: plaintext` روی `.num`.
6. Tab order = visual order (RTL)؛ تست کیبورد اجباری (a11y checklist).
7. Search box: `dir="auto"` روی `<input>` (اگر کاربر فارسی بزند RTL می‌شود؛ اگر لاتین، LTR).
8. URL/Canonical: `/page/12345` — هیچ جزء RTL در URL نیست (قاعدهٔ architecture: URL فقط اعداد/اسلاگ لاتین).

---

## ۶. Motion

- **Token‌های زمان:** `--dur-fast: 150ms`, `--dur-base: 200ms`, `--dur-slow: 300ms`؛ easing استاندارد: `cubic-bezier(0.2, 0, 0, 1)` (standard) و `cubic-bezier(0, 0, 0.2, 1)` (exit).
- **مجوز فقط:** (a) fade+shift 8–16px برای reveal بخش‌های home؛ (b) cross-fade 150ms برای prev/next page navigation؛ (c) drawer slide-inline 250ms؛ (d) skeleton pulse برای بارگذاری API.
- `@media (prefers-reduced-motion: reduce)` → همهٔ transition/animation صفر، skeleton ثابت، scroll-behavior auto. (طبق قاعدهٔ skill: reduced-motion = final state بلافاصله.)
- **حذف از MASTER:** اسنیپت GSAP/ScrollTrigger — این محصول بدون JS-framework است (§architecture)؛ همان رفتار با IntersectionObserver + CSS transition پیاده می‌شود (zero dependency).
- Hover: فقط `box-shadow`/`border-color`/`opacity` — **بدون** transform که layout جابه‌جا کند (anti-pattern MASTER).

---

## ۷. Component Language

### ۷.۱ Volume Card (کارت جلد)

```
┌────────────────────────────┐
│  [cover plate 3:4 SVG]     │   ← §۸: کاور تایپوگرافیِ نامعتبر
│  جلد 47                    │   ← Vazirmatn 700, --text-h3
│  ۹٬۳۹۱ صفحه · پوشش ۱۰۰٪  │   ← --text-sm, tabular-nums
│  [badge: کامل | در حال بازیابی] │
└────────────────────────────┘
```
- عرض کارت: 210px؛ گرید: 3 (mobile 375) / 4 (768) / 5 (1024) / 6 (1280) ستون، gap 16px.
- hover: `--shadow-md → --shadow-lg` (بدون translateY — anti-pattern layout-shift).
- جلد نامشخص (`volkeyd531f422`، volume_no=null): cover با «نامشخص» + badge `--color-warning` «در حال بازیابی شمارهٔ جلد».
- کل کارت `<a>` است (hit area کامل)؛ focus-visible: ring 2px `--color-focus-ring`, offset 2px.

### ۷.۲ Breadcrumb

`خانه › جلد 47 › برگ 3037` — `--text-sm`, رنگ itemها `--color-text-muted`، item فعلی `--color-text` + `aria-current="page"`. از ۲ سطح به بالا نمایش (قاعدهٔ skill: 3+ levels). جداکننده `›` mirror شده (در RTL جهت درست را خودش دارد).

### ۷.۳ Prev/Next Page Controls (قلب ریدر)

- دو دکمهٔ بزرگ (حداقل 48×44px) در پایین reader و یک mini-bar چسبان (sticky) بالای reader.
- لیبل: «برگ قبل (3036)» / «برگ بعد (3038)» + chevron mirror شده.
- **gap-aware:** اگر صفحهٔ بعدِ واقعی گم‌شده باشد (مثلاً 3037 در range گم‌شده)، دکمه می‌رود به نزدیک‌ترین موجود و یک chip کوچک `--color-warning` می‌گوید «۱۴ صفحه در این بازه در دست بازیابی است». هرگز شماره‌شکنی (numbering collapse) نمی‌شود (B-mission: numbering transparency).
- حالت empty/truncated: دکمه‌ها disabled نیستند (ناوبری همیشه ممکن است) — فقط محتوای صفحه وضعیت‌دار است.
- URL stable: `/page/<item_index>` — history.pushState برای prev/next (قاعدهٔ skill: back button قابل پیش‌بینی).

### ۷.۴ Metadata Drawer (metadata drawer)

- از inline-end، عرض 400px (mobile: full-screen sheet از پایین، 85vh)، slide 250ms.
- بخش‌ها: **هویت** (page_id, item_index, barg, volume, section) · **یکپارچگی** (SHA-256 content_hash — LTR island mono, کپی با یک کلیک) · **Provenance** (captured_at, source_page_id, source URL لینک) · **کیفیت** (status + flags) · **رابطه‌ها** (heading record id, next_page_id, children count).
- همهٔ hash/ID با `dir="ltr"` + mono + `user-select: all`.
- **قاعدهٔ امنیتی (B10):** هیچ فیلد `hidden_context`/`hidden_summary`/`retrieval_context` در drawer و هیچ‌جا در کلاینت رندر نمی‌شود؛ فقط idها (hctx:/hcctx:) نمایش داده می‌شوند، نه محتوای رکورد.

### ۷.۵ Quality/Status Badges

| وضعیت | رنگ متن/پس‌زمینه | لیبل فارسی |
|---|---|---|
| `ok` | `--color-success`/`--color-success-soft` | کامل |
| `short` | `--color-text-muted`/`--color-bg-subtle` | صفحهٔ کوتاه |
| `empty` | `--color-warning`/`--color-warning-soft` | بدون متن (در دست بازیابی) |
| `truncated_at_2000` | `--color-danger`/`--color-danger-soft` | **متن در منبع قطع است (۲۰۰۰ نویسه)** |
| `dup_item_index` | `--color-teal`/`--color-teal-soft` | تکرار شماره (نسخهٔ k) |
| missing range | `--color-warning`/`--color-warning-soft` | در دست بازیابی |

- Badge = `<span>` با متن (رنگ هرگز تنها حامل معنا). ارتفاع 24px، radius-sm.
- صفحهٔ truncated در reader: نوار بالای متن (banner) با توضیح: «این صفحه در منبعِ اصلی حداکثر ۲۰۰۰ نویسه ثبت شده است؛ ادامهٔ متن موجود نیست.» + link به وضعیت backfill.

### ۷.۶ Search Box + Results

- Box: radius-md، ارتفاع 48px، icon search inline-start، placeholder «در متن تفسیر جستجو کنید…»، `dir="auto"`.
- Debounce 300ms فقط برای autocomplete (V1: autocomplete اختیاری — core = submit + results).
- Result row: snippet با highlight `<mark>` (پس‌زمینه `#FDE9C8`، متن `--color-text`) + breadcrumb کوچک (جلد/برگ) + badge quality. Skeleton rows هنگام بارگذاری (aria-busy)؛ «نتیجه‌ای یافت نشد» با پیشنهاد (قاعدهٔ skill: dead-end ممنوع) — مثلاً «با کلمهٔ کوتاه‌تر یا بدون «تفصیر»/«تفسیر» دوباره تلاش کنید».
- Empty state: «نتیجه‌ای یافت نشد» + ۲ پیشنهاد (link به مباحث پرتکرار: تفسیر، بحث روایی) + لینک به راهنمای جستجو.

### ۷.۷ Buttons / Inputs (از MASTER، override شده)

```css
/* Primary — link/CTA: "خواندن", "ادامه" */
.btn-primary { background: #92400E; color: #fff; padding: 12px 24px;
  border-radius: var(--radius-md); font: 600 16px/1 Vazirmatn; }
.btn-primary:hover { background: #7C340D; }            /* بدون transform */
.btn-primary:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 2px; }

/* Secondary */
.btn-secondary { background: transparent; color: #92400E;
  border: 1.5px solid #92400E; padding: 12px 24px; border-radius: var(--radius-md); }
.btn-secondary:hover { background: #FBF0E2; }

/* Ghost (nav, icon) */
.btn-ghost { background: transparent; color: var(--color-text-muted); padding: 8px; }

/* Input */
.input { padding: 12px 16px; border: 1px solid var(--color-border);
  border-radius: var(--radius-md); font: 400 16px/1.4 Vazirmatn; background: var(--color-surface); }
.input:focus { border-color: var(--color-focus-ring); box-shadow: 0 0 0 3px rgba(15,92,84,0.15); outline: none; }
.input::placeholder { color: var(--color-text-faint); }
```
Touch target حداقل 44×44px همه‌جا.

### ۷.۸ Cover Plate (SVG تایپوگرافی — policy §۸)

- نسبت 3:4؛ پس‌زمینه: گرادیان بسیار ملایم از `#F3EFE7` به `#EDE6D9` + زینت هندسیِ اسلامیِ ساده (یک ستارهٔ ۸پرِ خطی ۱px در گوشهٔ inline-end، با `--color-accent` opacity 12%).
- محتوا: نام اثر (Amiri 700، «تفسیر تسنیم») · شمارهٔ جلد (Vazirmatn 700، بزرگ) · لیبل نسخه (Vazirmatn 400, `--text-xs`, `--color-text-muted`: «خروجی کراول hamta-2026»).
- **لیبل اجباری** پایین کاور: `نمایهٔ اختصاصی — جلد رسمی نیست` (Vazirmatn 400, 11px, `--color-text-faint`).
- تولید: **deterministic** — hash(volume_id) فقط برای seed زاویه/رنگ زینت؛ خروجی SVG با SHA ثابت برای همان ورودی؛ در build-time ساخته می‌شود (فایل استاتیک) — نه هر-request.

---

## ۸. سیاست تصویر (Image Policy — B3)

1. **هیچ عکس کاور رسمی/اسکن‌شده‌ای استفاده نمی‌شود** — چون منبع مجاز ندارد. همهٔ کاورها SVG تایپوگرافیِ **نمایه‌ای** هستند (§۷.۸) و با لیبل «نمایهٔ اختصاصی — جلد رسمی نیست» علامت‌گذاری شده‌اند. اگر بعداً منبع اسکن مجاز (licensed) ظاهر شود، جایگزینی با policy یک-to-one انجام می‌شود (فیلد `cover_source` در read-model از قبل تعریف شده — v1 همیشه `generated-svg`).
2. **اسکن صفحه وجود ندارد:** پیکره TEXT-only است؛ ریدر فقط متن را رندر می‌کند. هیچ تصویر اسکنِ جعلی، هیچ placeholder «عکس صفحه» مجاز نیست.
3. تصویرهای تنها در V1: SVG کاورها + SVG آیکون‌ها + SVG زینت (خط‌ها). **صفر** رستر.
4. هر SVG: `role="img"` + `<title>` فارسی (مثلاً «کاور جلد 47 — نمایهٔ اختصاصی») برای screen reader.

---

## ۹. دسترسی‌پذیری (Accessibility) — WCAG 2.1 AA

| هدف | پیاده‌سازی |
|---|---|
| کنتراست | §۲: همهٔ جفت‌های متن ≥4.5:1 (normal) / ≥3:1 (large)؛ non-text UI ≥3:1 — مقادیر در جدول‌ها ثبت شده |
| focus-visible | ring 2px `#0F5C54` offset 2px روی همهٔ controls؛ focus order = visual RTL order |
| کیبورد | تمام کارها (خواندن، prev/next، search، drawer، theme) بدون ماوس؛ trap ممنوع |
| reduced motion | §۶: همه‌چیز off در `prefers-reduced-motion: reduce` |
| touch | target ≥44px؛ gap بین targetهای همسایه ≥8px |
| heading hierarchy | h1 یک‌تایی هر صفحه؛ h2 برای بخش‌ها؛ skip-to-content link اولین focus |
| lang | `lang="fa"` روی html، `lang="ar"` روی آیات عربی، LTR islands با `dir` صریح |
| Screen reader | آیکون تزئینی `aria-hidden`؛ badgeها متن‌دار؛ skeleton با `aria-busy`؛ نتیجهٔ search با `role="status"` |
| Dynamic type | ریدر: `font-size: 19px` قابل تغییر با `text-size` (دکمهٔ A+/A− در reader، ذخیره در localStorage، محدوده 16–24px) — layout خراب نمی‌شود (measure ثابت ch) |
| رنگ-تنها ممنوع | badgeها متن + رنگ؛ prev/next با لیبل عددی |

**Breakpoints (mobile-first):** 375 (phone) → 768 (tablet) → 1024 (laptop) → 1280 (desktop). تست اجباری: 375px portrait + landscape، بدون horizontal scroll.

---

## ۱۰. Anti-Patterns (ممنوعیات صریح V1)

1. ❌ کلیشهٔ داشبورد مدیریتی: sidebar چپ پر آیکون، KPI card، جدول dense. (این محصول reader است.)
2. ❌ Glassmorphism / backdrop blur هر جا (MASTER هم بلور modal را دارد — حذف شد).
3. ❌ Emoji به‌عنوان آیکون.
4. ❌ عکس کاور/اسکنِ جعلی (policy §۸).
5. ❌ دادهٔ ساختگی: عدد آمار/درصد بدون منبع DB؛ صفحهٔ «خالی» که با متن نمونه پر شده باشد؛ سوره/مبحث بدون شواهد واقعی (§B6 verdict).
6. ❌ Hero-Centric landing با testimonial carousel (پترن MASTER برای این محصول بی‌معناست).
7. ❌ Layout-shifting hover (scale/translate روی کارت‌ها و دکمه‌ها).
8. ❌ متن full-width در reader (محدود 68ch).
9. ❌ CDN runtime (فونت/JS/CSS از بیرون) — offline-first.
10. ❌ JSON viewer / debug UI در مسیر عمومی (metadata drawer فقط فیلدهای public؛ `?debug` فقط در dev profile).
11. ❌ نمایش `hidden_context` در هر لایه‌ی public (خصوصیت امنیتی — test در §architecture).
12. ❌ رنگ به‌تنهایی به‌عنوان تنها سیگنال وضعیت.

---

## ۱۱. Pre-Delivery Checklist (برای فاز ۳)

- [ ] همهٔ مقادیر کنتراست §۲ در هر دو تم با ابزار اندازه‌گیری‌شده (فرض بردن ممنوع)
- [ ] 375px: بدون horizontal scroll؛ targetها ≥44px
- [ ] reduced-motion: skeleton/transition خاموش، scroll snap خاموش
- [ ] کیبورد: تمام سناریوی ۱۲ قدم E2E (سند architecture §۹.۳) بدون ماوس
- [ ] drawer از inline-end باز می‌شود؛ chevronها mirror شده‌اند
- [ ] همهٔ hash/URL mono + LTR + copy-to-clipboard
- [ ] cover SVGها deterministic (دو build متوالی → byte-identical)
- [ ] هیچ `hidden_context` در DOM عمومی (grep test)
- [ ] فونت‌ها self-hosted، no CDN request در network tab
- [ ] لیبل «نمایهٔ اختصاصی — جلد رسمی نیست» در همهٔ کاورها

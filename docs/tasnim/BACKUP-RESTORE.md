# بک‌آپ و بازیابی — Tasnim Web V1

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md) · عملیات: [OPS-RUNBOOK.md](OPS-RUNBOOK.md)

---

## ۱. چه چیزی باید بک‌آپ شود (و چه چیزی نه)

| لایه | مسیر | چرا بک‌آپ شود؟ | اندازهٔ خط پایه (v0003) |
|---|---|---|---|
| **read model** | `tasnim/data/readmodel/v0003/` | **حیاتی** — کل کتاب (45,844 صفحه) در این یک دایرکتوری است. بدون آن، سایت خالی است. | `tasnim_readmodel.db` 260,816,896 B + `build_meta.db` 12,288 B + `build.sha256` 168 B + `covers/` 6 SVG (≈ 9 KB) ≈ **261 MB** |
| **corpus source** | canonical corpus v0003 (روی s52 / پایپلاین — **نه در این worktree**) | **حیاتی اما جدا** — منبع immutable برای build. بک‌آپ آن تابع بک‌آپ‌های corpus/pipeline است، نه این سند. صریح: **corpus source جدا بک‌آپ می‌شود و با read model یکی نیست.** | GBها (pages.jsonl 170,629,785 B + heading-records.jsonl 9,857,675 B + …) |
| rate-limit | `tasnim_rate_limits.db` / volume `tasnim_runtime` | **غیرحیاتی** — state قابل‌تولید؛ حذفش = فقط reset شمارنده (موردی در [OPS-RUNBOOK.md](OPS-RUNBOOK.md) §4) | ≤ MBها |
| کد | git repo | با git + GitLab بک‌آپ می‌شود | — |

**مهم — identity read model فقط این‌هاست:** `tasnim_readmodel.db` + `build_meta.db` + `build.sha256` + `covers/`.
فایل `tasnim_rate_limits.db` که گاهی داخل دایرکتوری دیدید (وقتی سرور با `--rate-db` پیش‌فرض اجرا شده) **جزء identity نیست** و قابل حذف است (تست‌های این مأموریت با `--rate-db .tmp_phase6/ratelimit.db` اجرا شدند تا مدل آلوده نشود).

### زنجیرهٔ SHA (برای verify بک‌آپ)

```text
build.sha256 (sidecar، 2 سطر):
  <sha256>  tasnim_readmodel.db      ← 353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd
  <sha256>  build_meta.db            ← ed0f3d525c4a3e24819b233646fb2f46f30c287bd6e924062f8f75b75eedbbc0

build_meta.db.content_sha256:
  40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4   ← fingerprint خودِ build

canonical corpus (روی s52، verify شده در زمان build):
  pages.jsonl           8bec1bb8…9648755b  (170,629,785 B)
  heading-records.jsonl 0a1e52a5…1170b1aa  (9,857,675 B)
  corpus.json           8e71a395…f9f51b1   (19,846 B)
  manifest.json         0e50f52b…25cea60   (6,938 B, verify=false)
```

هر لایه روی لایهٔ قبل verify می‌شود: sidecar ← build_meta ← corpus. اگر یکی شکست، بک‌آپ معتبر نیست.

---

## ۲. بک‌آپ (دستور)

الگوی بک‌آپ سازمانی (AGENTS.md §3): قبل از هر تغییری + دوره‌ای هفتگی (در [OPS-RUNBOOK.md](OPS-RUNBOOK.md) §3).

```bash
TS=$(date +%Y%m%d-%H%M%S)
BK=/home/saber/backups

# 1) snapshot read model (read-only copy):
mkdir -p $BK
cp -a tasnim/data/readmodel/v0003 $BK/tasnim-readmodel-v0003-$TS

# 2) verify — باید دقیقاً با sidecar یکی باشد:
( cd $BK/tasnim-readmodel-v0003-$TS && sha256sum tasnim_readmodel.db build_meta.db )
diff <(cd $BK/tasnim-readmodel-v0003-$TS && sha256sum tasnim_readmodel.db build_meta.db \
       | awk '{print $1}' | tr '\n' ' ') \
     <(awk '{print $1}' tasnim/data/readmodel/v0003/build.sha256 | tr '\n' ' ' | sed 's/ $//')

# 3) snapshot stack (کد، بدون data):
tar czf $BK/tasnim-deploy-$TS.tar.gz \
  --exclude=tasnim/data --exclude='.git' tasnim/ docs/tasnim/

# 4) ثبت:
echo "$TS $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> $BK/tasnim-backups.log
```

### روی Windows (این host)

```powershell
# کپی:
Copy-Item -Recurse tasnim\data\readmodel\v0003 .tmp_phase6\bk-v0003
# verify:
Get-FileHash tasnim\data\readmodel\v0003\tasnim_readmodel.db -Algorithm SHA256
Get-FileHash .tmp_phase6\bk-v0003\tasnim_readmodel.db -Algorithm SHA256
# (هر دو باید 353f413b…d9c0fd بدهند)
```

---

## ۳. بازیابی (restore)

### سناریو A: خرابی/از دست رفتن read model

```text
1. بک‌آپ جدیدترین معتبر را پیدا کنید:
     ls -lt /home/saber/backups/tasnim-readmodel-v0003-*
2. verify بک‌آپ (قبل از هر چیز):
     cd $BK/tasnim-readmodel-v0003-$TS && sha256sum tasnim_readmodel.db
     # → باید 353f413b…d9c0fd باشد (یا با build.sha256 همان snapshot یکی)
3. جایگزینی (هرگز روی نسخهٔ فعال ننویسید؛ دایرکتوری را عوض کنید):
     mv tasnim/data/readmodel/v0003 tasnim/data/readmodel/v0003.corrupt
     cp -a $BK/tasnim-readmodel-v0003-$TS tasnim/data/readmodel/v0003
4. verify نهایی:
     sha256sum tasnim/data/readmodel/v0003/tasnim_readmodel.db
5. restart + smoke (بخش ۴)
6. اگر سبز: v0003.corrupt را بعد از یک دورهٔ پایداری (۱۲h+) حذف کنید
```

### سناریو B: rollback بعد از سواپ نسخهٔ ناموفق (v0004 → v0003)

این restore **نیست** — هر دو نسخه دست‌نخورده هستند:

```text
1. compose: bind mount v0004 → v0003
2. docker compose ... up -d tasnim-api && restart tasnim-web
3. smoke 15/15
```
(جزئیات کامل در [OPS-RUNBOOK.md](OPS-RUNBOOK.md) §7)

### سناریو C: خرابی corpus source

با restore بک‌آپ‌های corpus/pipeline (تابع آن زیرسیستم؛ خارج از این سند). بعد از restore، build دوباره ممکن است — read model فعلی (v0003) **تأثیر نمی‌گیرد** چون immutable و مستقل است.

---

## ۴. verify بازیابی (الزامی بعد از هر restore)

```bash
# 1) identity:
sha256sum tasnim/data/readmodel/v0003/tasnim_readmodel.db
# → 353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd

# 2) integrity:
sqlite3 tasnim/data/readmodel/v0003/tasnim_readmodel.db "PRAGMA integrity_check;"
# → ok

# 3) سرور + smoke کامل:
python -X utf8 -m tasnim.web.app --db tasnim/data/readmodel/v0003/tasnim_readmodel.db --port 5079 &
python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5079
# → 15 PASS / 0 FAIL

# 4) آمار (باید دقیقاً این اعداد باشند):
curl -sS http://127.0.0.1:5079/api/v1/tasnim/statistics
# → page_count 45844، heading_count 10739، topic_count 1080، volume_count 6
```

اگر هرکدام شکست خورد → restore کامل نشده؛ snapshot قبلی را برگردانید و ریشه‌یابی کنید.

---

## ۵. retention و چرخش

- **حداقل 3 snapshot** از read model نگه دارید (آخرین + 2 قبلی) تا خرابی تدریجی دیده شود.
- **هرگز snapshot را در-place overwrite نکنید** — هر بک‌آپ دایرکتوری/فایل جدید با TS.
- **log**: `tasnim-backups.log` (سطر: TS + SHA + اپراتور).
- **حجم**: هر snapshot ≈ 261 MB — 30 snapshot ماهیانه ≈ 8 GB.
- **corpus source**: تابع retention پایپلاین corpus (جدا).

---

## ۶. چه چیزی بک‌آپ **نمی‌شود** (و چرا مشکلی نیست)

| چیز | دلیل |
|---|---|
| rate-limit DB | قابل‌تولید؛ reset = دکمهٔ ایمن (OPS-RUNBOOK §4) |
| session/cookie | V1 stateless است (بدون user account) |
| cache | ETag strong + content-addressed است؛ با read model بازتولید می‌شود |
| build-report.json | **در v0003 وجود ندارد** (docstring builder اشاره می‌کند ولی build فعلی نساخته — ناسازگاری مصدق، یادداشت Phase 7). حتی اگر در v0004 بیاید، قابل‌تولید است (build report از build می‌آید). |
| `.tmp_phase6/` | شواهد مأموریت؛ قابل تولید/حذف |

---

## ۷. چک‌لیست تمرین restore (ربعی)

- [ ] یک snapshot واقعی گرفته و SHA verify شده
- [ ] restore روی دایرکتوری **جدا** (نه production) انجام شده
- [ ] smoke 15/15 روی snapshot restore شده سبز
- [ ] `statistics` دقیقاً 45,844 / 10,739 / 1,080 / 6 داده
- [ ] نتیجه در گزارش ثبت شده

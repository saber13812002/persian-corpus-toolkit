# احراز هویت داشبورد (PCM-09)

داشبورد داده‌های پیکره را با یک رمز عبور محافظت می‌کند. طراحی: **یک رمز، sessionهای
قابل باطل‌کردن، cookieهای امن، rate-limit روی ورود، بدون رمز در URL/Log/DB/Git.**

## چه چیزی محافظت می‌شود و چه چیزی باز می‌ماند

| Namespace | وضعیت | دلیل |
|-----------|-------|------|
| `GET /api/dashboard/*` | 🔒 401 بدون session | داده‌ی پیکره حساس است |
| `POST /api/auth/login` / `logout` | 🔓 (خودِ ورود) | — |
| `GET /api/auth/status` | 🔓 | UI برای نمایش overlay استفاده می‌کند |
| صفحه‌ی `/dashboard/` (HTML) | 🔓 | داده‌ها 401 می‌شوند؛ overlay ورود سمت کلاینت نمایش داده می‌شود |
| `POST /api/projects*` (create, points, pages, report) | 🔓 | **کراول زنده‌ی اکستنشن هرگز قطع نشود** |
| `GET /api/projects`، `/api/stats` و بقیه‌ی APIهای اکستنشن | 🔓 | همان دلیل |

## رمز عبور

- رمز **فقط** به‌صورت hash در جدول `auth_meta` (کلید `password_hash`) ذخیره می‌شود.
- الگوریتم: **scrypt** (n=16384, r=8, p=1, dklen=32) با ۱۶ بایت salt تصادفی برای هر hash.
  فرمت: `scrypt$<iterations>$<salt_hex>$<hash_hex>` — تأیید با `hmac.compare_digest`.
- رمز متنی فقط یک‌بار از متغیر محیطی سرور می‌آید:
  - `PCT_DASHBOARD_PASSWORD` (plaintext) — در `.env` سرور (gitignored، chmod 600)
  - یا `PCT_DASHBOARD_PASSWORD_HASH` (a hash پیش‌ساخته)
- `seed_password` فقط اگر hash ذخیره‌شده نباشد، مقدار را hash می‌کند و ذخیره می‌کند
  (`INSERT OR IGNORE`) — هیچ‌گاه plaintext در DB یا Git یا لاگ نمی‌ماند.
- **حالت توسعه**: اگر رمزی seed نشده باشد، endpointهای داشبورد باز می‌مانند
  (برای تست محلی) — در production حتماً `.env` تنظیم است.

## Sessionها

- `POST /api/auth/login` با `{ "password": "..." }` → اگر درست باشد، توکن
  ۳۲ بایتی `secrets.token_urlsafe` در جدول `auth_sessions` (انقضا ۷ روز) و
  cookie ارسال می‌شود.
- Cookie `pct_session`:
  - `HttpOnly` (جاوااسکریپت نمی‌تواند بخواند)
  - `Secure` اگر request از HTTPS آمده باشد (از `X-Forwarded-Proto` با ProxyFix)
  - `SameSite=Lax`
  - `Path=/`، `max_age` = ۷ روز
- `POST /api/auth/logout` → حذف session از DB → cookie بی‌اثر می‌شود (قابل باطل‌کردن).
- توکن **هرگز در URL** نمی‌رود (فقط در body/cookie).

## Rate-limit ورود

- DB-backed (جدول `auth_rate`): **۵ تلاش ناموفق در ۱۰ دقیقه** از هر IP → `429`.
- IP از `X-Forwarded-For` (با ProxyFix x_for=1) یا `remote_addr`.
- اولین خطای پنجم، شمارنده را در بازه‌ی جاری نگه می‌دارد؛ بعد از ۱۰ دقیقه
  شروع می‌کند. ورود موفق شمارنده را صفر می‌کند.

## Wiring

- `backend/auth.py`: `hash_password`, `verify_password`, `ensure_auth_schema`,
  `seed_password`, `make_require_auth(get_db)` (factory decorator), `register_auth_routes`.
- `backend/server.py`:
  - `app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)`
  - در `init_db()`: `ensure_auth_schema(db)` + `seed_password(db)`
  - ثبت روت‌ها در کنار `register_dashboard_routes`.

## تغییر رمز (production)

```bash
# 1) hash جدید بسازید (روی هر Python 3.10+):
python -c "import hashlib,secrets; s=secrets.token_bytes(16); d=hashlib.scrypt(b'NEW-PW',salt=s,n=16384,r=8,p=1,dklen=32); print('scrypt$16384$%s$%s'%(s.hex(),d.hex()))"

# 2) در سرور s52:
sqlite3 ~/saberprojects/persian-corpus-toolkit/backend/thesaurus.db \
  "UPDATE auth_meta SET value='<HASH-BAZA>' WHERE key='password_hash';"

# 3) همه‌ی sessionهای موجود بی‌اثر می‌شوند (با ریستارت بکند یا DELETE FROM auth_sessions)
```

> توصیه: بعد از تغییر رمز، `auth_sessions` را خالی کنید تا sessionهای قدیمی
> قطع شوند: `DELETE FROM auth_sessions;`

## تست‌ها

`backend/test_dashboard.py` → `A01..A08`:
- A01 status (auth_enabled=true، authenticated=false)
- A02 401 قبل از ورود · A03 رمز اشتباه · A04 ورود موفق + cookie
- A05 داده بعد از ورود · A06 خروج session را باطل می‌کند
- A07 بعد از ۵ شکست → 429 حتی با رمز درست
- A08 APIهای نوشتاری اکستنشن بدون auth باز می‌مانند (کراول زنده امن است)

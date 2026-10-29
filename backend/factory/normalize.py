"""factory.normalize — PersianNormalizer (stage 7, norm v1).

اصل: هر قانون جدا، قابل تنظیم، نسخه‌شده و تست‌پذیر است؛ و یک guard
صحت‌ساز اطمینان می‌دهد هیچ نویسه‌ی معناداری (حرف/عدد) حذف یا تغییر
معنایی نیابد. RAW هرگز تغییر نمی‌کند — فقط نسخه‌ی normalized.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

NORM_VERSION = "n-1"

# ---- نگاشت یکسان‌سازی نویسه‌های عربی→فارسی (سیاست پیش‌فرض) ----
ARABIC_TO_PERSIAN = {
    "\u0649": "\u06CC",  # ى عربی (alef maksura) -> ی فارسی
    "\u0643": "\u06A9",  # ک عربی (kaf)          -> ک فارسی (keh)
    # سیاست: فقط جفت‌های متغیر واقعی؛ ء/ة دست‌نخورده می‌مانند.
}

# نیم‌فاصله: فقط کلیتیک‌های واقعی و کم‌خطر (بلند→کوتاه برای alternation صحیح)
# «ش/م/ت» تک‌حرفی و «هست/است» (فعل‌ها) عمداً حذف شدند (خطر join کاذب).
_ZWNJ_SUFFIXES = (
    "ترین", "تر", "مان", "تان", "های", "ها", "ای", "ات", "ان", "ی",
)
# نیم‌فاصله فقط بین «کلمهٔ فارسی کامل» و پسوند، نه وسط کلمهٔ عربی/فارسی:
# lookahead باید پایان کلمه واقعی باشد (space/end/punctuation) — حرف بعدی مجاز نیست.
_ZWNJ_RE = re.compile(
    r"([\u0621-\u064A\u067E\u0686\u0698\u06A9\u06AF\u0688])"   # حرف فارسی/عربی
    r"[\s\u00A0]+"
    r"(" + "|".join(_ZWNJ_SUFFIXES) + r")"
    r"(?=[\s\u00A0،؛.:؟!«»\"()\[\]{}]|$)"
)

_SPACE_RE = re.compile(r"[ \t\u00A0\u2009\u200A\u2002\u2003]+")
_ZWSP_RE = re.compile(r"[\u200B\uFEFF]")
_RLM_RE = re.compile(r"[\u200E\u200F]")
_DIGIT_MAP = {
    "keep": {},
    "persian": {str(i): chr(0x06F0 + i) for i in range(10)},
    "ascii": {chr(0x06F0 + i): str(i) for i in range(10)},
}
_AR_INDIC = {chr(0x0660 + i) for i in range(10)}  # ٠-٩
_FA_DIGITS = {chr(0x06F0 + i) for i in range(10)}  # ۰-۹


@dataclass
class NormalizationPolicy:
    """سیاست نسخه‌شده‌ی نرمال‌سازی — هر قانون قابل خاموش/روشن و تنظیم است.

    nfkc **پیش‌فرض خاموش** است: NFKC علامت‌های تکیه را تغییر می‌دهد
    (مثلا‌ ّ U+0651 → َ U+064E) — این تغییر محتوایی است و با اصل
    «پرهیز از تغییر معنی» در تعارض است؛ فقط اگر خواسته شد فعال شود.
    """
    version: str = NORM_VERSION
    nfkc: bool = False
    arabic_to_persian: bool = True
    zwnj: bool = True
    collapse_spaces: bool = True
    strip_zwsp: bool = True
    strip_rlm: bool = True
    digits: str = "keep"          # keep | persian | ascii
    digits_map: dict = field(default_factory=dict)  # override

    def __post_init__(self):
        if self.digits not in _DIGIT_MAP:
            raise ValueError(f"digits policy نامعتبر: {self.digits}")

    def rules(self) -> list[str]:
        on = []
        if self.nfkc: on.append("nfkc")
        if self.arabic_to_persian: on.append("arabic_to_persian")
        if self.zwnj: on.append("zwnj")
        if self.collapse_spaces: on.append("collapse_spaces")
        if self.strip_zwsp: on.append("strip_zwsp")
        if self.strip_rlm: on.append("strip_rlm")
        if self.digits != "keep": on.append(f"digits:{self.digits}")
        return on

    def policy_dict(self) -> dict:
        """نگاشت کامل سیاست (برای ثبت در manifest — PCM-14C.3).

        ثبت کامل policy در manifest باعث می‌شود هر اجرا بدون دسترسی به کد
        بازمی‌گردد: سیاست دقیق نرمال‌سازی همان اجرا ثبت است.
        """
        return {
            "version": self.version,
            "nfkc": self.nfkc,
            "arabic_to_persian": self.arabic_to_persian,
            "zwnj": self.zwnj,
            "collapse_spaces": self.collapse_spaces,
            "strip_zwsp": self.strip_zwsp,
            "strip_rlm": self.strip_rlm,
            "digits": self.digits,
            "rules": self.rules(),
        }


class PersianNormalizer:
    def __init__(self, policy: NormalizationPolicy | None = None):
        self.policy = policy or NormalizationPolicy()
        self._dmap = self.policy.digits_map or _DIGIT_MAP[self.policy.digits]

    # ---------- اعمال هر قانون به‌صورت جدا ----------
    def _r_nfkc(self, t: str) -> str:
        return unicodedata.normalize("NFKC", t)

    def _r_arabic(self, t: str) -> str:
        return "".join(ARABIC_TO_PERSIAN.get(c, c) for c in t)

    def _r_zwnj(self, t: str) -> str:
        prev = None
        while prev != t:
            prev = t
            t = _ZWNJ_RE.sub(lambda m: m.group(1) + "\u200C" + m.group(2), t)
        return t

    def _r_spaces(self, t: str) -> str:
        t = _SPACE_RE.sub(" ", t)
        t = t.replace(" \n", "\n").replace("\n ", "\n")
        return t.strip()

    def _r_zwsp(self, t: str) -> str:
        return _ZWSP_RE.sub("", t)

    def _r_rlm(self, t: str) -> str:
        return _RLM_RE.sub("", t)

    def _r_digits(self, t: str) -> str:
        if not self._dmap:
            return t
        out = []
        for c in t:
            if c in self._dmap:
                out.append(self._dmap[c])
            elif self.policy.digits == "persian" and c in _AR_INDIC:
                out.append(chr(0x06F0 + (ord(c) - 0x0660)))
            else:
                out.append(c)
        return "".join(out)

    _RULES = {
        "nfkc": "_r_nfkc",
        "arabic_to_persian": "_r_arabic",
        "zwnj": "_r_zwnj",
        "collapse_spaces": "_r_spaces",
        "strip_zwsp": "_r_zwsp",
        "strip_rlm": "_r_rlm",
        "digits": "_r_digits",
    }

    def normalize(self, text: str) -> tuple[str, dict]:
        """بازگشت (normalized_text, stats هر قانون). ترتیب اعمال ثابت است."""
        stats: dict[str, int] = {}
        t = text
        for rule in self.policy.rules():
            name = rule.split(":")[0]
            fn = getattr(self, self._RULES[name])
            t2 = fn(t)
            if t2 != t:
                stats[rule] = abs(len(t2) - len(t)) or 1
            t = t2
        return t, stats


_DIGIT_INV = {chr(0x06F0 + i): str(i) for i in range(10)}
_DIGIT_INV.update({chr(0x0660 + i): str(i) for i in range(10)})


def letters_digits_only(t: str) -> str:
    """حذف space/ZWNJ/ZWSP/RLM + کاننیکال‌سازی ارقام برای مقایسه‌ی «بدون تغییر معنی»."""
    out = []
    for c in t:
        if c in " \t\u00A0\u200B\u200C\u200D\u200E\u200F\uFEFF\u0020":
            continue
        if unicodedata.category(c).startswith("C") and c not in "\n":
            continue
        out.append(_DIGIT_INV.get(c, c))
    return "".join(out)


def verify_no_semantic_change(raw: str, normalized: str) -> list[str]:
    """guard: هیچ حرف/عددی حذف، اضافه یا جابه‌جا نشده باشد.

    (تغییر مجاز: space/ZWNJ/zero-width + نگاشت‌های یکسان‌سازی نویسه
     که خودشان در آرایه‌ی معرّف‌شده‌اند + سیاست ارقام.)
    """
    issues = []
    a = letters_digits_only(raw)
    b = letters_digits_only(normalized)
    # کاننیکال‌سازی یک‌طرفه (عربی→فارسی) روی **هر دو طرف** —
    # (معکوس‌نما کردن اشتباه است: نمی‌توان گفت یک ی فارسی از عربی آمده یا نه)
    a = "".join(ARABIC_TO_PERSIAN.get(c, c) for c in a)
    b = "".join(ARABIC_TO_PERSIAN.get(c, c) for c in b)
    # معادلت NFKC روی هر دو طرف: اگر قانون nfkc روشن باشد، تفاوت‌های
    # «معادل یونی‌کود» (تکیه‌ها) نباید به‌عنوان تغییر معنی شمرده شوند.
    a = unicodedata.normalize("NFKC", a)
    b = unicodedata.normalize("NFKC", b)
    if a != b:
        for i, (ca, cb) in enumerate(zip(a, b)):
            if ca != cb:
                issues.append(f"char_changed_at={i} raw='{ca}' norm='{cb}'")
                break
        else:
            issues.append(f"length_changed raw={len(a)} norm={len(b)}")
    return issues

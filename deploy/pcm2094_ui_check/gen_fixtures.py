# -*- coding: utf-8 -*-
"""Generate N small Persian .docx fixtures for the real-UI check (2.3).

Usage: python gen_fixtures.py <out_dir> [n]
Prints FIXTURES_OK <n> on success.
"""
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from factory._smoke_fixtures import make_docx  # noqa: E402


def main() -> None:
    out = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    os.makedirs(out, exist_ok=True)
    for i in range(1, n + 1):
        make_docx(os.path.join(out, "kitab-%02d.docx" % i), [
            ("Normal", "عنوان: کتاب آزمایشی شماره %d" % i),
            ("Normal", "نویسنده: نویسنده نمونه"),
            ("Normal", "ناشر: انتشارات نمونه"),
            ("Heading 1", "فصل اول"),
            ("Normal", "پاراگراف فارسی اول کتاب %d. English mixed too." % i),
            ("Normal", "پاراگراف دوم با عدد 2026 و عدد ۱۴۰۵ در یک خط."),
            ("Heading 2", "بخش ۱"),
            ("Normal", "متن زیربخش با فاصلهٔ   اضافی و\tتب."),
            ("Heading 1", "فصل دوم"),
            ("Normal", "متن فصل دوم کتاب %d." % i),
        ])
    print("FIXTURES_OK", n)


if __name__ == "__main__":
    main()

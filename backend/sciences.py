# Shared thesaurus science categories (from /fa/api/elastic/search FacetList)
# API currently exposes 13 sciences covering ~352k items total.
THESAURUS_SCIENCES = [
    ("040", "معرفت‌شناسی"),
    ("050", "منطق"),
    ("060", "منطق رواقی"),
    ("070", "فلسفه اسلامی"),
    ("080", "فلسفه اشراق"),
    ("090", "فلسفه دین"),
    ("100", "فلسفه اخلاق"),
    ("110", "فلسفه حقوق"),
    ("120", "فلسفه سیاسی"),
    ("140", "کلام"),
    ("150", "معرفت‌شناسی عرفانی"),
    ("170", "عرفان نظری"),
    ("180", "عرفان عملی"),
]

THESAURUS_SCIENCE_IDS = [s[0] for s in THESAURUS_SCIENCES]

# Main content types in the same index
THESAURUS_MAIN_TYPES = [
    ("term", "اصطلاح‌نامه"),
    ("category", "کلیدواژه و نمایه"),
    ("grammer", "قواعد و اصول"),  # API spelling
]

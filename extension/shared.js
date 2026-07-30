// Shared constants (classic script — no ES modules)
var PCT = window.PCT || {};
PCT.BACKEND = 'http://127.0.0.1:5055';
PCT.ELASTIC_URL = 'https://thesaurus.eiis.iki.ac.ir/fa/api/elastic/search';
PCT.THESAURUS_BASE = 'https://thesaurus.eiis.iki.ac.ir';
PCT.KHAMENEI_HOST = 'farsi.khamenei.ir';
PCT.PAGE_SIZE = 100;
PCT.THESAURUS_SCIENCES = [
  { id: '040', title: 'معرفت‌شناسی' },
  { id: '050', title: 'منطق' },
  { id: '060', title: 'منطق رواقی' },
  { id: '070', title: 'فلسفه اسلامی' },
  { id: '080', title: 'فلسفه اشراق' },
  { id: '090', title: 'فلسفه دین' },
  { id: '100', title: 'فلسفه اخلاق' },
  { id: '110', title: 'فلسفه حقوق' },
  { id: '120', title: 'فلسفه سیاسی' },
  { id: '140', title: 'کلام' },
  { id: '150', title: 'معرفت‌شناسی عرفانی' },
  { id: '170', title: 'عرفان نظری' },
  { id: '180', title: 'عرفان عملی' },
];
PCT.THESAURUS_SCIENCE_IDS = PCT.THESAURUS_SCIENCES.map(function (s) { return s.id; });
window.PCT = PCT;

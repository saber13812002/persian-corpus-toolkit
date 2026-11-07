# -*- coding: utf-8 -*-
"""Tasnim Web V1 — OpenAPI 3.1 spec + offline docs (PCM-20.6.4 §5.3).

Served at /api/v1/tasnim/openapi.json and /api/v1/tasnim/docs.
Offline: the docs page is a minimal local HTML shell that fetches
openapi.json from the same origin and renders a readable contract
browser — no CDN, no network (documented deviation from full Swagger UI).
"""

CANONICAL_BASE = "https://tasnim.ai.ismc.ir"

COMMON_PARAMS = {
    "limit": {"name": "limit", "in": "query", "schema": {"type": "integer",
                 "default": 50, "maximum": 200}, "description": "Page size (max 200)"},
    "offset": {"name": "offset", "in": "query", "schema": {"type": "integer",
                 "minimum": 0}, "description": "Row offset"},
    "page_token": {"name": "page_token", "in": "query", "schema": {"type": "string"},
                 "description": "Opaque cursor (base64 offset) from meta.next_page_token"},
}

PAGINATION = {
    "properties": {"items": {"type": "array", "items": {"type": "object"}},
                   "total": {"type": "integer"}},
}


def _err(name, title, code, status):
    return {
        "name": name,
        "description": title,
        "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Error"},
            "example": {
                "type": CANONICAL_BASE + "/errors/" + name,
                "title": title, "status": status, "code": code,
                "message": "…", "details": {}, "request_id": "req_…",
            },
        }},
    }


def spec(version="unknown", content_sha=""):
    p = COMMON_PARAMS
    page_item = {
        "type": "object",
        "properties": {
            "page_id": {"type": "string"},
            "item_index": {"type": "integer"},
            "dup_rank": {"type": "integer"},
            "volume": {"type": "object",
                       "properties": {
                           "volume_id": {"type": "string"},
                           "volume_no": {"type": ["integer", "null"]},
                           "title": {"type": "string"},
                           "attribution": {"enum": ["recorded", "ambiguous"]},
                           "ambiguity": {"type": "boolean"}}},
            "barg": {"type": ["integer", "null"]},
            "heading": {"anyOf": [{"type": "object", "properties": {
                "record_id": {"type": "string"}, "text": {"type": "string"},
                "next_page_id": {"type": ["string", "null"]}}},
                {"type": "null"}]},
            "visible_content": {"type": "object", "properties": {
                "text": {"type": "string"}, "char_count": {"type": "integer"},
                "record_class": {"type": "string"}}},
            "next_page_reference": {"$ref": "#/components/schemas/PageRef"},
            "previous_page_reference": {"$ref": "#/components/schemas/PageRef"},
            "metadata": {"type": "object", "properties": {
                "page_id": {"type": "string"}, "content_sha256": {"type": "string"},
                "captured_at": {"type": "string"},
                "source_page_id": {"type": "integer"},
                "section": {"type": "string"},
                "source_url": {"type": "string"}}},
            "quality": {"type": "object", "properties": {
                "status": {"type": "string"},
                "flags": {"type": "array", "items": {"type": "string"}},
                "truncated_at_source": {"type": "boolean"},
                "source_char_cap": {"type": ["integer", "null"]}}},
            "duplicates": {"type": "array", "items": {"type": "object",
                "properties": {"dup_rank": {"type": "integer"},
                                "page_id": {"type": "string"},
                                "volume_id": {"type": "string"}}}},
            "reference": {"type": "object", "properties": {
                "work_id": {"type": "string"}, "edition_id": {"type": "string"},
                "volume_id": {"type": "string"},
                "volume_no": {"type": ["integer", "null"]},
                "item_index": {"type": "integer"},
                "barg": {"type": ["integer", "null"]},
                "page_id": {"type": "string"},
                "content_sha256": {"type": "string"},
                "source_url": {"type": "string"},
                "canonical_url": {"type": "string"}}},
            "rag_status": {"const": "not_connected"},
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Tasnim Web V1 API (read model)",
            "version": "1.0.0",
            "description": (
                "Read-only API on the tasnim read model (SQLite FTS5). "
                "Corpus version: %s (content_sha256=%s). "
                "Persian full-text search: pre-tokenization tokenize_fa/1.0, "
                "unicode61, prefix AND queries, bm25; no Persian stemming "
                "(documented). rag_status is always not_connected — no RAG "
                "in V1. /surahs returns 503 SURAH_INDEX_NOT_SUPPORTED "
                "(honest: 0/114 canonical coverage in v0003)."
                % (version, content_sha or "…")),
        },
        "servers": [{"url": CANONICAL_BASE + "/api/v1/tasnim"},
                    {"url": "http://127.0.0.1:5071/api/v1/tasnim",
                     "description": "local runbook (Windows dev)"}],
        "tags": [{"name": "catalog"}, {"name": "volumes"}, {"name": "pages"},
                 {"name": "topics"}, {"name": "surahs"}, {"name": "search"},
                 {"name": "meta"}],
        "paths": {
            "/catalog": {
                "get": {"tags": ["catalog"], "summary": "Identity + global counts",
                        "operationId": "catalog",
                        "responses": {"200": {"description": "OK",
                            "content": {"application/json": {"schema": {
                                "type": "object", "properties": {
                                    "data": {"type": "object"},
                                    "meta": {"$ref": "#/components/schemas/Meta"}}}}}}}
            }},
            "/volumes": {
                "get": {"tags": ["volumes"], "summary": "List volumes (6 in v0003)",
                        "operationId": "volumesList",
                        "parameters": [p["limit"], p["offset"], p["page_token"],
                                        {"name": "sort", "in": "query",
                                         "schema": {"enum": ["volume_no", "page_count"],
                                                     "default": "volume_no"}}],
                        "responses": {"200": {"description": "OK"},
                                      "400": {"$ref": "#/components/responses/BadRequest"}}},
            },
            "/volumes/{volume_id}": {
                "get": {"tags": ["volumes"], "summary": "Volume detail",
                        "operationId": "volumeDetail",
                        "parameters": [{"name": "volume_id", "in": "path",
                                         "required": True, "schema": {"type": "string"}}],
                        "responses": {"200": {"description": "OK"},
                                      "404": {"$ref": "#/components/responses/VolumeNotFound"}}},
            },
            "/surahs": {
                "get": {"tags": ["surahs"],
                        "summary": "Surah index — honest unavailable",
                        "operationId": "surahs",
                        "responses": {
                            "503": {"description": "Not supported in v0003",
                                    "content": {"application/json": {
                                        "schema": {"$ref": "#/components/schemas/Error"},
                                        "example": {
                                            "type": CANONICAL_BASE +
                                            "/errors/surah-index-not-supported",
                                            "title": "Surah index not supported",
                                            "status": 503,
                                            "code": "SURAH_INDEX_NOT_SUPPORTED",
                                            "message": "در پیکرهٔ v0003 هیچ مارکر مطمئن سوره وجود ندارد: فیلد surah در schema نیست؛ 0 هدر با پیشوند سخت سوره؛ پوشش canonical 0/114",
                                            "details": {"status": "not_supported",
                                                        "coverage": "0/114"},
                                            "request_id": "req_…"}}}}}},
            },
            "/surahs/{surah_id}": {
                "get": {"tags": ["surahs"], "summary": "Surah detail — honest unavailable",
                        "operationId": "surahDetail",
                        "parameters": [{"name": "surah_id", "in": "path",
                                         "required": True, "schema": {"type": "string"}}],
                        "responses": {"503": {"description": "Not supported in v0003",
                                               "content": {"application/json": {
                                                   "schema": {"$ref": "#/components/schemas/Error"}}}}}},
            },
            "/topics": {
                "get": {"tags": ["topics"], "summary": "List topics (normalized)",
                        "operationId": "topicsList",
                        "parameters": [p["limit"], p["offset"], p["page_token"],
                                        {"name": "q", "in": "query",
                                         "schema": {"type": "string"},
                                         "description": "Prefix on normalized_text"},
                                        {"name": "min_pages", "in": "query",
                                         "schema": {"type": "integer"}},
                                        {"name": "sort", "in": "query",
                                         "schema": {"enum": ["page_count", "name"],
                                                     "default": "page_count"}}],
                        "responses": {"200": {"description": "OK"},
                                      "400": {"$ref": "#/components/responses/BadRequest"}}},
            },
            "/topics/{topic_id}": {
                "get": {"tags": ["topics"], "summary": "Topic detail + occurrences",
                        "operationId": "topicDetail",
                        "parameters": [
                            {"name": "topic_id", "in": "path", "required": True,
                             "schema": {"type": "string", "pattern": "^t-[0-9a-f]{12}$"}},
                            p["limit"], p["offset"], p["page_token"]],
                        "responses": {"200": {"description": "OK"},
                                      "404": {"$ref": "#/components/responses/TopicNotFound"}}},
            },
            "/pages/{item_index}": {
                "get": {"tags": ["pages"],
                        "summary": "Page reader (heart of the contract)",
                        "operationId": "page",
                        "parameters": [
                            {"name": "item_index", "in": "path", "required": True,
                             "schema": {"type": "integer", "minimum": 0}},
                            {"name": "dup_rank", "in": "query",
                             "schema": {"type": "integer", "default": 0}}],
                        "responses": {
                            "200": {"description": "OK",
                                    "content": {"application/json": {
                                        "schema": {"type": "object",
                                                    "properties": {
                                                        "data": page_item,
                                                        "meta": {"$ref": "#/components/schemas/Meta"}}}}},
                            "400": {"$ref": "#/components/responses/BadRequest"},
                            "404": {"$ref": "#/components/responses/PageNotFound"}}},
            }},
            "/pages/{item_index}/neighbors": {
                "get": {"tags": ["pages"],
                        "summary": "Gap-aware prev/next by item_index order",
                        "operationId": "pageNeighbors",
                        "parameters": [{"name": "item_index", "in": "path",
                                         "required": True, "schema": {"type": "integer"}}],
                        "responses": {"200": {"description": "OK"},
                                      "404": {"$ref": "#/components/responses/PageNotFound"}}},
            },
            "/search": {
                "get": {"tags": ["search"], "summary": "Persian full-text search",
                        "operationId": "search",
                        "parameters": [
                            {"name": "q", "in": "query", "required": True,
                             "schema": {"type": "string", "minLength": 2,
                                         "maxLength": 64}},
                            p["limit"], p["offset"], p["page_token"],
                            {"name": "volume_id", "in": "query",
                             "schema": {"type": "string"}},
                            {"name": "sort", "in": "query",
                             "schema": {"enum": ["relevance", "item_index"],
                                         "default": "relevance"}}],
                        "responses": {"200": {"description": "OK (total=-1+estimated for ≥3 tokens)"},
                                      "400": {"$ref": "#/components/responses/BadRequest"}}},
            },
            "/statistics": {
                "get": {"tags": ["meta"],
                        "summary": "Real counters with written definitions",
                        "operationId": "statistics",
                        "responses": {"200": {"description": "OK"}}},
            },
            "/health": {
                "get": {"tags": ["meta"], "summary": "Liveness + readmodel identity",
                        "operationId": "health",
                        "responses": {"200": {"description": "OK"}}},
            },
            "/openapi.json": {
                "get": {"tags": ["meta"], "summary": "This spec",
                        "operationId": "openapi",
                        "responses": {"200": {"description": "OpenAPI 3.1 JSON"}}},
            },
            "/docs": {
                "get": {"tags": ["meta"],
                        "summary": "Offline contract browser (local HTML, no CDN)",
                        "operationId": "docs",
                        "responses": {"200": {"description": "HTML"}}},
            },
        },
        "components": {
            "schemas": {
                "Meta": {"type": "object", "properties": {
                    "request_id": {"type": "string"},
                    "readmodel": {"type": "object", "properties": {
                        "version": {"type": "string"},
                        "content_sha256": {"type": "string"}}},
                    "generated_at": {"type": "string", "format": "date-time"},
                    "next_page_token": {"type": "string"},
                }},
                "Error": {"type": "object", "properties": {
                    "type": {"type": "string"}, "title": {"type": "string"},
                    "status": {"type": "integer"}, "code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {"type": "object"},
                    "request_id": {"type": "string"}}},
                "PageRef": {"type": "object", "properties": {
                    "item_index": {"type": ["integer", "null"]},
                    "page_id": {"type": ["string", "null"]},
                    "exists": {"type": "boolean"},
                    "gap_before": {"type": "integer"},
                    "reason": {"type": "string"},
                    "in_missing_range": {"type": "array",
                                          "items": {"type": "integer"},
                                          "minItems": 2, "maxItems": 2},
                    "next_available_item_index": {"type": "integer"},
                    "prev_available_item_index": {"type": "integer"},
                    "gap": {"type": "object"},
                }},
            },
            "responses": {
                "BadRequest": _err("invalid-parameter", "Bad request",
                                    "INVALID_PARAMETER", 400),
                "PageNotFound": {
                    "description": "No page at item_index",
                    "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                        "example": {
                            "type": CANONICAL_BASE + "/errors/page-not-found",
                            "title": "Page not found", "status": 404,
                            "code": "PAGE_NOT_FOUND",
                            "message": "صفحه‌ای با item_index 99999 در پیکره وجود ندارد.",
                            "details": {"item_index": 99999,
                                        "in_missing_range": None,
                                        "suggestion": "نزدیک‌ترین صفحات موجود: …"},
                            "request_id": "req_…"}}},
                },
                "VolumeNotFound": _err("volume-not-found", "Volume not found",
                                        "VOLUME_NOT_FOUND", 404),
                "TopicNotFound": _err("topic-not-found", "Topic not found",
                                       "TOPIC_NOT_FOUND", 404),
            },
        },
    }


DOCS_HTML = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tasnim Web V1 — API contract (offline)</title>
<style>
:root { --bg:#FAF7F2; --surface:#FFF; --text:#1C1917; --muted:#57534E;
        --faint:#78716C; --border:#E5DED2; --ink:#92400E; --accent:#D97706; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font-family:'Noto Naskh Arabic',serif; line-height:1.7; }
header { background:linear-gradient(#F3EFE7,#EDE6D9); padding:24px 32px;
         border-bottom:1px solid var(--border); }
h1 { margin:0 0 4px; font-family:Amiri,serif; font-size:26px; }
.sub { color:var(--muted); font-size:14px; }
main { padding:24px 32px; max-width:1100px; margin:0 auto; }
.op { background:var(--surface); border:1px solid var(--border);
      border-radius:10px; margin-bottom:12px; }
.op h3 { margin:0; padding:10px 16px; font-size:15px; display:flex; gap:10px;
         align-items:center; border-bottom:1px solid var(--border);
         font-family:'Vazirmatn',sans-serif; }
.op .body { padding:12px 16px; color:var(--muted); font-size:13.5px; }
.method { display:inline-block; background:var(--ink); color:#fff;
          font-family:Consolas,monospace; font-size:11px; padding:2px 8px;
          border-radius:6px; }
path { font-family:Consolas,monospace; direction:ltr; unicode-bidi:embed; }
code { font-family:Consolas,monospace; direction:ltr; unicode-bidi:embed;
       background:#F3EFE7; padding:1px 5px; border-radius:4px; font-size:12px; }
.err { color:#B91C1C; }
a { color:var(--ink); }
</style>
</head>
<body>
<header>
<h1>کتاب‌خانهٔ دیجیتال تسنیم — قرارداد API (V1)</h1>
<div class="sub" id="sub">در حال بارگذاری مشخصه…</div>
</header>
<main id="list"><p>در حال بارگذاری…</p></main>
<script>
(function () {
  var ENT = {"&": 38, "<": 60, ">": 62, '"': 34, "'": 39};
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return "&#x" + ENT[c].toString(16) + ";";
    });
  }
  function fmt(v) {
    if (v === null || v === undefined) return "null";
    if (typeof v === "object") {
      if (Array.isArray(v)) return "[" + v.map(fmt).join(", ") + "]";
      return "{" + Object.keys(v).map(function (k) {
        return esc(k) + ": " + fmt(v[k]);
      }).join(", ") + "}";
    }
    return typeof v === "string" ? "\"" + esc(v) + "\"" : String(v);
  }
  fetch("/api/v1/tasnim/openapi.json", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (spec) {
      document.getElementById("sub").textContent =
        spec.info.title + " · " + spec.info.version +
        " · " + (spec.info.description || "");
      var list = document.getElementById("list");
      list.innerHTML = "";
      var order = Object.keys(spec.paths);
      order.forEach(function (path) {
        Object.keys(spec.paths[path]).forEach(function (method) {
          var op = spec.paths[path][method];
          var div = document.createElement("div");
          div.className = "op";
          var h3 = document.createElement("h3");
          var m = document.createElement("span");
          m.className = "method";
          m.textContent = method.toUpperCase();
          var p = document.createElement("code");
          p.textContent = method.toUpperCase() + " " + path;
          h3.appendChild(m); h3.appendChild(p);
          var body = document.createElement("div");
          body.className = "body";
          body.textContent = op.summary || "";
          var ps = op.parameters || [];
          if (ps.length) {
            var pl = document.createElement("p");
            pl.innerHTML = "پارامترها: " + ps.map(function (x) {
              return "<code>" + esc(x.name) + "</code>(" + esc(x.in) + ")";
            }).join("، ");
            body.appendChild(pl);
          }
          Object.keys(op.responses || {}).forEach(function (code) {
            var r = op.responses[code];
            var rl = document.createElement("p");
            rl.innerHTML = "<code>" + code + "</code> " + esc(r.description || "");
            body.appendChild(rl);
          });
          div.appendChild(h3); div.appendChild(body);
          list.appendChild(div);
        });
      });
    })
    .catch(function (e) {
      document.getElementById("list").innerHTML =
        '<p class="err">خطا در بارگذاری مشخصه: ' + esc(e) + "</p>";
    });
})();
</script>
</body>
</html>
"""

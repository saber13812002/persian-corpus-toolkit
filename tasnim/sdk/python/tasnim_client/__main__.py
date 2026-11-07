# -*- coding: utf-8 -*-
"""tasnim_client CLI demo (PCM-20.6.4).

Exercises the SDK against a running server and prints compact JSON
(summarized) for each endpoint — the same calls an integrator would
make. Read-only; never mutates anything.

Usage:
    python -m tasnim_client                      # https://tasnim.ai.ismc.ir
    python -m tasnim_client --base http://127.0.0.1:5071
    python -m tasnim_client --page 2 --search "قرآن" --topic t-xxxx

Exit code 0 on success, 1 on any API/transport error (printed, not
raised).
"""
import argparse
import json
import sys

from . import TasnimAPIError, TasnimClient, TasnimClientError


def _summary(obj, **kw):
    out = dict(obj) if isinstance(obj, dict) else {}
    out.update(kw)
    return out


def _short_page(p):
    return _summary(
        {},
        item_index=p.item_index, page_id=p.page_id, barg=p.barg,
        volume=p.volume_id, char_count=p.char_count,
        quality=p.quality_status, flags=p.flags,
        next=p.next_item_index, prev=p.previous_item_index,
        canonical_url=p.canonical_url,
    )


def run(base_url, page=None, search=None, topic=None, timeout=30):
    c = TasnimClient(base_url, timeout=timeout)
    out = {}

    h = c.get_health()
    out["health"] = _summary(h.data, request_id=h.request_id)

    cat = c.get_catalog()
    out["catalog"] = _summary(
        {}, work=cat.data["work"]["name"], edition=cat.data["edition"]["name"],
        counts=cat.data["counts"], coverage=cat.data["coverage"])

    vols = list(c.iter_volumes(limit=5))
    out["volumes"] = _summary(
        {}, count=len(vols),
        first=[_summary({}, volume_id=v["volume_id"], volume_no=v["volume_no"],
                        title=v["title"], page_count=v["page_count"])
               for v in vols[:3]])

    if vols:
        v = c.get_volume(vols[0]["volume_id"])
        out["volume_detail"] = _summary(
            {}, volume_id=v.data["volume_id"], page_count=v.data["page_count"],
            top_headings=v.data["top_headings"][:2])

    if page is not None:
        p = c.get_page(page)
        out["page"] = _short_page(p)

    nb = c.get_page_neighbors(0 if page is None else int(page))
    out["neighbors"] = _summary(
        {}, current=nb.data["current"],
        prev=nb.data["prev"].get("item_index"),
        next=nb.data["next"].get("item_index"))

    s = c.search(search if search else "قرآن")
    res = s.data
    out["search"] = _summary(
        {}, q=res["query"]["raw"], total=res["total"],
        estimated=res.get("estimated", False),
        hits=[_summary({}, item_index=r["item_index"],
                       page_id=r["page_id"]) for r in res["results"][:3]])

    t = c.get_topic(topic) if topic else None
    if t:
        out["topic"] = _summary(
            {}, topic_id=t.topic_id, display_text=t.display_text,
            occurrences_total=t.occurrences_total,
            occurrences=[o["item_index"] for o in t.occurrences[:5]])
    else:
        # Single page on purpose: iter_topics() would walk the full
        # token chain (e.g. 1080 topics) and trip the read rate limit.
        top = c.list_topics(limit=5)
        tops = top.data["items"]
        out["topics"] = _summary(
            {}, count=top.data["total"], shown=len(tops),
            first=[_summary({}, topic_id=t["topic_id"],
                            display_text=t["display_text"],
                            page_count=t["page_count"]) for t in tops[:3]])

    st = c.get_statistics().data
    out["statistics"] = _summary(
        {}, item_index=st["item_index"], quality_status=st["quality_status"])

    # honest unavailability demo (expected 503)
    try:
        c.get_surahs()
        out["surahs"] = "unexpected 200"
    except TasnimAPIError as e:
        out["surahs"] = _summary(
            {}, status=e.status, code=e.code,
            coverage=e.details.get("coverage"))

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Tasnim Web V1 SDK demo (read-only).")
    ap.add_argument("--base", default="https://tasnim.ai.ismc.ir",
                    help="server root (default: the public V1 host)")
    ap.add_argument("--page", type=int, default=None,
                    help="fetch this item_index (e.g. 2)")
    ap.add_argument("--search", default=None,
                    help="search query (default: قرآن)")
    ap.add_argument("--topic", default=None,
                    help="topic_id to show instead of the top list")
    ap.add_argument("--timeout", type=float, default=30)
    args = ap.parse_args(argv)
    try:
        return run(args.base, page=args.page, search=args.search,
                   topic=args.topic, timeout=args.timeout)
    except (TasnimAPIError, TasnimClientError) as e:
        print(json.dumps(
            {"error": repr(e),
             "code": getattr(e, "code", None),
             "status": getattr(e, "status", None),
             "request_id": getattr(e, "request_id", None)},
            ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

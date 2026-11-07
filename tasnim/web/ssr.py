# -*- coding: utf-8 -*-
"""Tasnim Web V1 — SSR blueprint (Flask + Jinja, no client framework).

Routes (architecture §6):
    GET /                       — work intro, volume grid, coverage panel,
                                  topic highlights, quick search, latest pages
    GET /volumes                — all volumes, real counts + covers
    GET /volumes/<volume_id>    — cover, stats, paginated headings + page index
    GET /page/<int:item_index>  — reader (missing index -> honest 200 state)
    GET /topics                 — paginated topic list
    GET /topics/<topic_id>      — topic detail (occurrences, disclaimer)
    GET /surahs                 — «در حال تکمیل», no fabrication
    GET /search?q=              — SSR FTS5 (invalid q -> 400 page, never 500)
    GET /about                  — corpus provenance, SHAs, limitations
    404 / 500                    — styled HTML (handled in create_app)

Data access: templates NEVER touch SQLite; every model comes from
``tasnim.web.pages`` (which uses the shared read-only connection).
SSR pages are NOT rate limited (the API contract limits /api/v1/tasnim;
rendering local pages of one's own read model is exempt — documented).
"""
from flask import Blueprint, render_template, request

from tasnim.web import pages


def make_ssr_blueprint(state):
    bp = Blueprint("ssr", __name__)

    @bp.app_context_processor
    def _context():
        return {"site": pages.site_context(pages.get_db(state), state)}

    @bp.get("/")
    def home():
        db = pages.get_db(state)
        return render_template("home.html", m=pages.home_model(db, state))

    @bp.get("/volumes")
    def volumes():
        db = pages.get_db(state)
        sort = request.args.get("sort", "volume_no")
        m = pages.volumes_model(db, state, sort=sort)
        return render_template("volumes.html", m=m)

    @bp.get("/volumes/<path:volume_id>")
    def volume_detail(volume_id):
        db = pages.get_db(state)
        m = pages.volume_detail_model(db, state, volume_id,
                                      page=request.args.get("p"))
        if m is None:
            raise pages.Ssr404(
                "جلدی با volume_id «%s» در read model نیست." % volume_id)
        return render_template("volume_detail.html", m=m)

    @bp.get("/page/<int:item_index>")
    def page(item_index):
        db = pages.get_db(state)
        try:
            dup_rank = int(request.args.get("dup_rank", 0))
        except (TypeError, ValueError):
            dup_rank = 0
        if dup_rank < 0:
            dup_rank = 0
        m = pages.page_model(db, state, item_index, dup_rank=dup_rank)
        if m.get("missing"):
            return render_template("page_missing.html", m=m)
        return render_template("page.html", m=m)

    @bp.get("/topics")
    def topics():
        db = pages.get_db(state)
        m = pages.topics_model(db, q=request.args.get("q"),
                               sort=request.args.get("sort", "page_count"),
                               page=request.args.get("p"))
        return render_template("topics.html", m=m)

    @bp.get("/topics/<topic_id>")
    def topic_detail(topic_id):
        db = pages.get_db(state)
        m = pages.topic_detail_model(db, topic_id,
                                     page=request.args.get("p"))
        if m is None:
            raise pages.Ssr404(
                "موضوعی با topic_id «%s» وجود ندارد." % topic_id)
        return render_template("topic_detail.html", m=m)

    @bp.get("/surahs")
    def surahs():
        return render_template("surahs.html", m=pages.surahs_model())

    @bp.get("/search")
    def search():
        db = pages.get_db(state)
        try:
            m = pages.search_model(db, request.args.get("q"))
        except pages.SsrError as e:
            return render_template("error.html",
                                   status=e.status, title=e.title,
                                   message=e.message, error=e), e.status
        return render_template("search.html", m=m)

    @bp.get("/about")
    def about():
        db = pages.get_db(state)
        return render_template("about.html", m=pages.about_model(db, state))

    return bp

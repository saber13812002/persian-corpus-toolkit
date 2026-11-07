# syntax=docker/dockerfile:1
# =============================================================================
# PCM-20.6.4 (B12) — Tasnim Web V1: read-model API image
# -----------------------------------------------------------------------------
# Design (docs/PCM-20.6.4-ARCHITECTURE.md §7):
#   * image = application code + REAL Python dependencies only.
#     Verified import surface of tasnim/web/* is Flask (-> Jinja2, Werkzeug,
#     MarkupSafe, blinker, click, itsdangerous) + stdlib (sqlite3, urllib,
#     json, hashlib). NO pandas, NO requests, NO runtime network access.
#   * NO data is baked into the image. The read model is mounted READ-ONLY at
#     /data (bind: /data/readmodel -> <repo>/tasnim/data/readmodel/v0003).
#   * The only writable runtime state is the rate-limit DB, which lives in a
#     dedicated writable volume at /var/tasnim (-> /var/tasnim/ratelimit.db).
#   * non-root user (uid 10001); no secrets, tokens, or keys anywhere.
#
# Build (context = this directory, tasnim/):
#   docker build -t tasnim-api:pcm2064 tasnim/
# or via compose (tasnim/docker-compose.tasnim.yml):
#   docker compose -f tasnim/docker-compose.tasnim.yml up -d --build
#
# Run standalone (after building the image):
#   docker run --rm --name tasnim-api \
#     -v "$PWD/tasnim/data/readmodel/v0003:/data/readmodel:ro" \
#     -v tasnim_runtime:/var/tasnim -p 127.0.0.1:5071:5071 tasnim-api:pcm2064
# =============================================================================

FROM python:3.12-slim

# Optional build-time PyPI mirror (docs/tasnim/DOCKER.md §6: hosts that cannot
# reach pypi.org directly — e.g. SSL-blocked networks — pass
#   --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
# Default is the official index (no mirror required when it is reachable).
ARG PIP_INDEX_URL=https://pypi.org/simple

# Runtime environment. TASNIM_DB_PATH is the ONLY app-relevant env var;
# the CMD below passes the same path explicitly (belt and braces).
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TASNIM_DB_PATH=/data/readmodel/tasnim_readmodel.db

WORKDIR /app

# Application code only — the `tasnim` package (web/, __init__.py).
# data/, e2e/, nginx/ are excluded via .dockerignore (see that file).
COPY . /app/tasnim/

# Real dependency set, pinned to the versions verified against this codebase
# (Flask 3.1.3 / Jinja2 3.1.6 / Werkzeug 3.1.9). Stdlib covers everything else.
RUN pip install --no-cache-dir "Flask==3.1.3"

# Non-root runtime user.
#   /data       — read-only mount point for the read model (runtime-provided)
#   /var/tasnim — writable runtime volume: rate-limit DB (wired in the CMD)
RUN useradd --create-home --uid 10001 tasnim \
    && mkdir -p /data /var/tasnim \
    && chown -R tasnim:tasnim /app /var/tasnim

USER tasnim

# Container-internal only; whether the host publishes 5071 is a compose
# decision (it does NOT — see docker-compose.tasnim.yml).
EXPOSE 5071

# Health probe = the real API health endpoint: a read-only query against the
# mounted read model (exempt from rate limiting by design).
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -X utf8 -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5071/api/v1/tasnim/health', timeout=8).status == 200 else 1)"

# Standalone server entry (tasnim/web/app.py). --host 0.0.0.0 is required for
# the compose network (edge nginx -> this container); 5071 is not published
# to the host, so this never widens the attack surface.
ENTRYPOINT ["python", "-X", "utf8", "-m", "tasnim.web.app"]
CMD ["--db", "/data/readmodel/tasnim_readmodel.db", \
     "--host", "0.0.0.0", "--port", "5071", \
     "--rate-db", "/var/tasnim/ratelimit.db"]

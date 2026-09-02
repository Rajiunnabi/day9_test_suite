# =====================================================================
# Backend image — FastAPI (task-tracker-api)
# Two stages: "builder" installs dependencies, "runtime" only carries the
# result. The final image never contains uv, compilers, or build caches.
# =====================================================================

# ---------------------------------------------------------------- builder
FROM python:3.12-slim AS builder

# uv is copied in as a single binary from its official image.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency files ONLY, first. This layer is reused on every rebuild where
# pyproject.toml/uv.lock did not change — which is nearly every code change.
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-dev --no-install-project

# Application code comes after, because it changes most often. Everything
# below this line is rebuilt on a code change; everything above is cached.
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --no-dev

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

# Don't run as root. If the app is ever compromised, the attacker lands as an
# unprivileged user instead of owning the container.
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
EXPOSE 8000

# Docker uses this to mark the container healthy/unhealthy. /health comes from
# app/api/v1/meta.py.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# No --reload here: this is the production command. The dev override swaps it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
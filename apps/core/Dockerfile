# syntax=docker/dockerfile:1.7

# ═══════════════════════════════════════════════════════════════════════
#  Venv nằm ở /opt/venv, KHÔNG nằm trong /app.
#  Lý do: target dev bind-mount ./apps/core lên /app, nếu venv ở /app
#  thì bind mount sẽ che mất nó.
# ═══════════════════════════════════════════════════════════════════════

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.5.24 /uv /uvx /usr/local/bin/

WORKDIR /app

# ── Lớp dependency, cache riêng khỏi source ────────────────────────────
FROM base AS deps
COPY pyproject.toml ./
COPY uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# ── Dev: hot reload, tự chạy migration khi khởi động ──────────────────
FROM deps AS dev
RUN --mount=type=cache,target=/root/.cache/uv uv sync
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# ── Prod: user không phải root, không reload ───────────────────────────
FROM deps AS prod
COPY . .
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app app \
    && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"]

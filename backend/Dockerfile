# syntax=docker/dockerfile:1.7
# MarketSignal backend image (API, worker and migration entrypoints share it).
FROM python:3.13-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependency layer (cached until pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Code and venv stay root-owned (read-only for the runtime user); no chown layer duplication.
RUN useradd --system --uid 10001 --no-create-home app
USER app

ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "marketsignal.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

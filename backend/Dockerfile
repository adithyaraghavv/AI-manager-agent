# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

# Install uv (single static binary) from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# System deps needed by common Python wheels (psycopg, cffi, etc.).
# Version pins deliberately omitted so the base image's package snapshot
# controls versions — pinning here would ratchet against Debian's stable
# security channel and go stale fast. Follow-up if reproducibility matters:
# switch to a distroless-style multi-stage build.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest(s) first for better layer caching.
# The uv.lock glob is tolerant: it matches zero files if the lockfile
# has not been generated yet, so the build stays green during migration
# to project-mode uv.
COPY backend/requirements.txt ./
COPY backend/pyproject.toml backend/uv.lock* ./

# If a pyproject exists we prefer `uv sync --frozen` (project mode).
# Otherwise fall back to compat mode against requirements.txt.
RUN if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev; \
    else \
        uv pip install --system -r requirements.txt; \
    fi

# Copy the rest of the backend source tree.
COPY backend/ ./

EXPOSE 8000

# Default command — overridden by docker-compose for the migrations service.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

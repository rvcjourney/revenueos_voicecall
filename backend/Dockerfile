# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# gcc + libpq-dev are needed to compile asyncpg and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install into /install so Stage 2 can copy only the packages (not the build tools)
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# libpq5: runtime PostgreSQL client library (asyncpg needs it)
# curl: used by the HEALTHCHECK
# postgresql-client: provides pg_dump, used by the worker/beat containers for
# the daily database backup task (app/workers/tasks/backup.py) — not needed
# by the api container, but the same image is used for all three, so it's
# installed here rather than maintained as a second Dockerfile.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled packages from builder
COPY --from=builder /install /usr/local

# Non-root user with a home directory
RUN useradd -r -m -s /bin/false motm

# Celery beat keeps its schedule file here (a named volume in
# docker-compose.yml). A new volume takes this directory's ownership, so it
# must belong to the non-root user or beat cannot write its schedule.
RUN mkdir -p /var/lib/celerybeat && chown motm:motm /var/lib/celerybeat

COPY --chown=motm:motm . .

USER motm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 4 uvicorn workers under gunicorn for CPU-bound headroom.
# Increase --workers via GUNICORN_WORKERS env var for larger VPS instances.
CMD ["gunicorn", "app.main:app", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--workers", "4", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "120", \
    "--graceful-timeout", "30", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--log-level", "warning"]

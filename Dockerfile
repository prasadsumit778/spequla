# Production image for the FastAPI backend. Python 3.12 per CLAUDE.md
# section 6. Two-stage build: compile dependencies once, ship a slim runtime
# image with no compiler toolchain in it.
#
# Runtime env vars expected (see docs/deployment.md): DATABASE_URL,
# OBJECT_STORE_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET, WORKOS_API_KEY,
# WORKOS_CLIENT_ID. None are baked in here -- this image is identical
# whether it's pointed at a pilot tenant's schema or a production one.
#
# This same image also runs migrations (see docs/deployment.md) via
# `python -m db.migrations.runner` as a distinct step before a deploy, not
# as part of the API container's own startup -- multiple API instances
# starting simultaneously must never race to apply migrations.

FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime

RUN groupadd --system spequla && useradd --system --gid spequla --create-home spequla
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app
# Only what the app needs at runtime: no corpus/ (only config/, the
# generated artefact, is read -- see src/config/loader.py), no synthetic/,
# no tests/, no web/. See .dockerignore for the full exclusion list.
COPY src/ ./src/
COPY config/ ./config/
COPY db/migrations/ ./db/migrations/
COPY scripts/seed_dim_date.py scripts/seed_entity.py scripts/create_tenant.py scripts/link_tenant_workos_org.py ./scripts/

RUN chown -R spequla:spequla /app
USER spequla

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8000') + '/health', timeout=3)" || exit 1

# Shell form so ${PORT} expands -- most managed platforms (Cloud Run, Render,
# Railway, Fly) inject PORT and expect the app to bind to it.
CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}

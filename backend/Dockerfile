# Multi-Stage-Build fuer den Bank Workflow Service Backend.
# Phase 1 / Commit 1.

# --- Stage 1: Build -----------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Build-Tools nur in der Builder-Stage; aus dem finalen Image fliegt das raus.
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /build/
COPY app /build/app

RUN pip install --no-cache-dir --upgrade pip wheel \
 && pip wheel --no-cache-dir --wheel-dir /build/wheels .

# --- Stage 2: Runtime ---------------------------------------------------------
FROM python:3.11-slim AS runtime

# Non-root-User; das Image laeuft nicht als root.
RUN useradd --create-home --uid 1001 --shell /bin/bash app
WORKDIR /app

COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/*.whl \
 && rm -rf /tmp/wheels

# Anwendungs-Code, Schemas und Alembic-Setup
COPY --chown=app:app app /app/app
COPY --chown=app:app schemas /app/schemas
COPY --chown=app:app legacy_demo /app/legacy_demo
COPY --chown=app:app alembic /app/alembic
COPY --chown=app:app alembic.ini /app/alembic.ini

USER app
EXPOSE 8000

# Liveness-Check: Root-Endpoint antwortet mit Status. /health kommt mit Auth in Commit 2.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
  sys.exit(0 if urllib.request.urlopen('http://localhost:8000/').status == 200 else 1)"

# Beim Container-Start: Migrationen anwenden, dann den FastAPI-Server starten.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

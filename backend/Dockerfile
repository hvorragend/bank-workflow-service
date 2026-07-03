# Multi-Stage-Build fuer den Bank Workflow Service Backend.
# Phase 1 / Commit 1.

# --- Stage 1: Build -----------------------------------------------------------
# Konservativ auf den Patch-Level gepinnt (S-011) — nicht auf ein bewegliches
# 3.11-slim-Tag. Beim Anheben zusaetzlich requirements.lock neu erzeugen.
FROM python:3.11.13-slim AS builder

WORKDIR /build

# Build-Tools nur in der Builder-Stage; aus dem finalen Image fliegt das raus.
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.lock /build/
COPY app /build/app

# Reproduzierbarer Build (O-001): Erst die exakt gepinnte Laufzeit-Closure aus
# dem Lockfile als Wheels bauen, dann die App selbst OHNE erneute
# Dependency-Aufloesung (--no-deps) — so gewinnen ausschliesslich die
# Lock-Versionen, nicht die (offenen) Floors aus pyproject.toml.
RUN pip install --no-cache-dir --upgrade pip wheel \
 && pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.lock \
 && pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels .

# --- Stage 2: Runtime ---------------------------------------------------------
FROM python:3.11.13-slim AS runtime

# sqlite3-CLI fuer das Online-Backup (F-006): deploy/backup/sqlite_backup.sh
# ruft `sqlite3 .backup` IN diesem Container auf. Ohne das Binary schlaegt
# jedes Backup fehl. --no-install-recommends haelt das Image klein.
RUN apt-get update \
 && apt-get install --no-install-recommends -y sqlite3 \
 && rm -rf /var/lib/apt/lists/*

# Non-root-User; das Image laeuft nicht als root.
RUN useradd --create-home --uid 1001 --shell /bin/bash app
WORKDIR /app

COPY --from=builder /build/wheels /tmp/wheels
COPY requirements.lock /tmp/requirements.lock
# --no-index: NUR aus den lokal gebauten Wheels installieren (offline,
# deterministisch). Zuerst die gepinnte Laufzeit-Closure aus dem Lockfile,
# dann die App selbst (--no-deps) — beide liegen als Wheel in /tmp/wheels.
RUN pip install --no-cache-dir --no-index --find-links /tmp/wheels \
        -r /tmp/requirements.lock \
 && pip install --no-cache-dir --no-index --no-deps --find-links /tmp/wheels \
        bank-workflow-service \
 && rm -rf /tmp/wheels /tmp/requirements.lock

# Anwendungs-Code, Schemas und Alembic-Setup
COPY --chown=app:app app /app/app
COPY --chown=app:app schemas /app/schemas
COPY --chown=app:app alembic /app/alembic
COPY --chown=app:app alembic.ini /app/alembic.ini

# SQLite-Datenverzeichnis als Mountpunkt fuer das persistente Volume.
RUN mkdir -p /app/data && chown app:app /app/data

USER app
EXPOSE 8000

# Liveness-Check via /health — Prozess- und HTTP-Erreichbarkeit, ohne DB-Touch.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
  sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"

# Beim Container-Start: Migrationen anwenden, dann den FastAPI-Server starten.
#
# --proxy-headers + --forwarded-allow-ips=* (F-015): Der Service laeuft hinter
# einem Reverse-Proxy (nginx/Traefik). Ohne diese Flags sieht uvicorn nur die
# Proxy-IP, wodurch der Rate-Limiter (slowapi) alle Clients als eine einzige
# IP zaehlt. Mit den Flags wird X-Forwarded-For ausgewertet und die echte
# Client-IP durchgereicht. WICHTIG: forwarded-allow-ips=* ist nur sicher, weil
# der Container-Port nicht direkt exponiert ist, sondern ausschliesslich hinter
# dem vertrauenswuerdigen Proxy im internen Compose-Netz haengt (siehe
# deploy/README.md, Abschnitt Produktions-Haertung).
#
# WICHTIG (S-007): Genau EIN Worker. Der APScheduler ist ein In-Process-
# Singleton — mehrere Worker wuerden SLA-Eskalationen doppelt ausloesen.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*' --log-level \"${LOG_LEVEL:-info}\""]

# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.
Format lose angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

Die maßgebliche Versionsnummer steht in `backend/pyproject.toml` und
`web/package.json` (aktuell `0.3.0`) — dieser Changelog referenziert sie, ist
aber nicht die Single Source of Truth für die Version.

## [Unbestimmt] — Vereinfachte Inbetriebnahme

Ein frischer Clone startet jetzt ohne manuelle Vorarbeiten durch — bisher
scheiterte der Erststart, weil weder ein Admin in der DB noch eine
`config/emergency_users.json` existierte (deren Erstellung einen lokal
erzeugten argon2-Hash erforderte).

### Hinzugefügt

- **Automatischer Initial-Admin** (`bootstrap.ensure_initial_admin`): Bei
  leerer DB ohne Notfall-Datei legt der Start genau einen lokalen Admin an
  (Username via `INITIAL_ADMIN_USERNAME`, Default `admin`). Ohne
  `INITIAL_ADMIN_PASSWORD` wird ein Einmal-Passwort generiert und nach
  `/app/data/initial-admin-password.txt` (chmod 600) geschrieben. Die Anlage
  wird als `auth.user.bootstrap` auditiert. Brownfield-sicher: existierende
  Admins, vorhandene Notfall-Dateien und vergebene Usernamen führen zum Skip —
  Passwörter werden nie überschrieben.
- **`deploy/prod-up.sh`**: Ein-Befehl-Inbetriebnahme für den Prod-Basis-Stack
  (Secrets-Bootstrap, Start ohne Mailpit, Healthcheck-Wait,
  Härtungs-Warnungen, Anzeige der Initial-Admin-Zugangsdaten).
- `dev-up.sh` zeigt nach dem Start die Initial-Admin-Zugangsdaten an, falls
  eine Erstinbetriebnahme stattfand.

### Geändert

- `deploy/.env.example` und Compose dokumentieren `INITIAL_ADMIN_USERNAME` /
  `INITIAL_ADMIN_PASSWORD`; Härtungs-Checkliste um „Initial-Admin-Passwort
  geändert / Datei gelöscht" ergänzt.

## [Unbestimmt] — Audit-Umsetzung

Umsetzung der Findings aus dem Betriebs-/Sicherheits-Audit. Betrifft nur
Deployment, Build, Doku und CI — keine fachlichen Änderungen an der Anwendung.

### Sicherheit

- **python-multipart** Floor auf `>=0.0.18` angehoben (CVE-2024-53981,
  DoS über Multipart-Parsing). (O-001)
- **Reverse-Proxy/Client-IP** (F-015): uvicorn startet mit
  `--proxy-headers --forwarded-allow-ips=*`, damit der Rate-Limiter (slowapi)
  die echte Client-IP sieht statt der Proxy-IP.
- **Produktions-Härtung** (F-025/F-026, S-009): neue Env-Schalter
  `REFRESH_COOKIE_SECURE`, `CORS_ALLOW_ORIGINS`, `SEED_DEMO_DATA`,
  `TRUST_PROXY_HEADERS`, `LOG_LEVEL` in `deploy/.env.example` und Compose
  dokumentiert; Härtungs-Checkliste in `deploy/README.md`.
- **Kein Mail-Catcher in Prod** (S-003): MailHog aus dem Haupt-Compose entfernt
  und als Mailpit in ein Dev-Override `deploy/docker-compose.dev.yml` ausgelagert;
  Ports an `127.0.0.1` gebunden. Web-Port ebenfalls an `127.0.0.1` gebunden.

### Betrieb & Backups

- **SQLite-Backup funktionsfähig** (F-006): `sqlite3`-CLI wird im
  Backend-Image installiert; `sqlite_backup.sh` nutzt `sqlite3 .backup`
  (WAL-konsistent) mit `PRAGMA integrity_check` und holt den Snapshot per
  `docker compose cp` statt über fragiles `cat`.
- **Storage-Backup robuster** (F-024): `storage_backup.sh` löst den
  Volume-Namen über die Docker-API auf und tart aus einem Wegwerf-Container,
  statt einen hartkodierten Host-Pfad anzunehmen.
- **Runbook korrigiert** (S-004): `docs/runbooks/backup_restore.md` von
  Postgres (nicht existent) auf den echten SQLite-Stack umgeschrieben, inkl.
  WAL-/SHM-Hinweisen beim Restore.
- **Single-Worker dokumentiert** (S-007): APScheduler ist In-Process-Singleton
  → genau 1 uvicorn-Worker (`--workers 1`), nicht horizontal skalieren.

### Build & Reproduzierbarkeit

- **Lockfile-Build** (O-001): `backend/requirements.lock` mit gepinnter
  Laufzeit-Closure; Dockerfile installiert daraus (`pip install -r
  requirements.lock`) + App mit `--no-deps`. Basis-Image auf `python:3.11.13-slim`
  konservativ gepinnt.
- **Tote Dependency entfernt** (O-010): `python-statemachine` (nirgends
  importiert) aus `pyproject.toml` entfernt.
- **alembic.ini abgesichert** (S-013): Fallback-`sqlalchemy.url` zeigt auf eine
  offensichtliche Sackgassen-Datei, damit ein Fehlaufruf ohne `DATABASE_URL`
  nicht unbemerkt eine leere DB migriert.

### Qualität & CI

- **CI eingeführt** (S-001): `.github/workflows/ci.yml` mit Backend-Job
  (pytest, ruff/mypy advisory) und Frontend-Job (tsc, vitest, build, Node 20/22)
  plus optionalem Docker-Build-Smoke.
- **ruff + mypy konfiguriert** (S-006): `[tool.ruff]`/`[tool.mypy]` in
  `pyproject.toml` mit pragmatischen Defaults.

### Compose-Robustheit

- **Healthcheck-Abhängigkeit & Logging** (S-011): `web` wartet auf
  `backend`-`service_healthy`; rotierende json-file-Logs (max-size/max-file)
  für beide Services.

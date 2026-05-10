# Deployment-Stack

Ein einziges Compose-File. Backend (SQLite) + Web (React/Nginx) + MailHog
(Mail-Catcher fuer Dev und Mail-Tests).

## Schnellstart

```bash
./deploy/dev-up.sh
```

Das Skript erzeugt beim ersten Lauf `deploy/.env` mit echten Secrets,
baut die Container und wartet auf den Backend-Healthcheck.

Endpunkte nach dem Start:

- React-Frontend:   <http://localhost:8000>
- OpenAPI / Swagger: <http://localhost:8000/docs>
- MailHog (Mail-UI): <http://localhost:8025>

Stoppen mit `./deploy/dev-down.sh` (Volumes bleiben), oder
`./deploy/dev-down.sh --volumes` für einen frischen Start.

## Was `bootstrap-env.sh` macht

`JWT_SECRET` (64 Hex) und `CONFIG_ENCRYPTION_KEY` (44 Base64-Fernet) haben
unterschiedliche Formate. Wer einen Wert im falschen Format setzt — ein
klassischer Fehler ist `openssl rand -hex 32` für den Fernet-Key — landet
in einem Crash-Loop. Das Skript:

1. Legt `deploy/.env` aus `.env.example` an, falls noch nicht vorhanden.
2. Erkennt jeden noch unveränderten Platzhalter (`replace-with-...`) und
   ersetzt ihn durch einen frisch erzeugten Zufallswert im richtigen Format.
3. Fasst bestehende Werte nicht an — kann beliebig oft ausgeführt werden.

Voraussetzung: `bash`, `openssl`. Kein Python notwendig.

## Manuelles Hochfahren ohne Wrapper-Skript

```bash
./deploy/bootstrap-env.sh
docker compose -f deploy/docker-compose.yml up -d --build
```

## Production-Deployment auf Proxmox

Vorgesehen ist ein Single-Host-Setup auf einer Linux-VM unter Proxmox:

1. VM bereitstellen (Ubuntu 24.04 LTS empfohlen), Docker Engine installieren.
2. Repo pullen, `./deploy/bootstrap-env.sh` für Secret-Generierung ausführen
   (oder `deploy/.env` manuell mit produktiven Werten füllen).
3. `docker compose -f deploy/docker-compose.yml up -d --build`
4. Reverse-Proxy / TLS davorschalten (z. B. Traefik oder nginx auf dem Host).

Backups (relevant für MaRisk AT 7.2 / DORA Art. 11):

- `backup/sqlite_backup.sh` — SQLite-Online-Snapshot via `sqlite3 .backup`
  (konsistent auch bei laufenden Schreibzugriffen)
- `backup/storage_backup.sh` — `tar.gz` des Anhang-Volumes
- `backup/cron.example` — Beispiel-Crontab mit 30-Tage-Aufbewahrung
- Proxmox Backup Server für die VM-Ebene als zweites Standbein
- Restore-Tests gehören in die Notfalldokumentation

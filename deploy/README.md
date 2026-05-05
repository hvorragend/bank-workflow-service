# Deployment-Stack

Zwei Compose-Files, beide cross-platform (Windows mit Docker Desktop und Linux nativ).

## `docker-compose.dev.yml` — Entwicklungs-Hilfsdienste

Postgres + MailHog. Backend laeuft daneben nativ. Empfohlen fuer den taeglichen
Entwicklungs-Loop.

```bash
docker compose -f deploy/docker-compose.dev.yml up -d
# Postgres:  localhost:5432  (User bws, Passwort bws_local_dev, DB bws)
# MailHog:   http://localhost:8025
```

## `docker-compose.yml` — Komplettstack (Postgres + Backend)

Dient zum Testen des deploybaren Container-Aufbaus. Spaeter (Commit 3) kommen
ein `web`-Service und Traefik als Reverse-Proxy dazu.

```bash
cp deploy/.env.example deploy/.env   # Passwort eintragen
docker compose -f deploy/docker-compose.yml up -d --build
# Anwendung: http://localhost:8000
```

## Production-Deployment auf Proxmox

Vorgesehen ist ein Single-Host-Setup auf einer Linux-VM unter Proxmox:

1. VM bereitstellen (Ubuntu 24.04 LTS empfohlen), Docker Engine installieren.
2. Repo pullen, `deploy/.env` mit produktiven Werten anlegen.
3. `docker compose -f deploy/docker-compose.yml pull && docker compose ... up -d`
4. Reverse-Proxy / TLS folgt mit Commit 3 (Traefik).

Backups (relevant fuer MaRisk AT 7.2 / DORA Art. 11):

- `pg_dump`-Cron mit Volume-Mount auf das Host-System
- Proxmox Backup Server fuer die VM-Ebene als zweites Standbein
- Restore-Tests gehoeren in die Notfalldokumentation (Phase 3)

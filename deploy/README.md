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
# Einmalig: deploy/.env anlegen und alle Pflicht-Geheimnisse generieren.
# Idempotent — bei wiederholtem Aufruf werden bereits gesetzte Werte nicht
# ueberschrieben.
./deploy/bootstrap-env.sh

docker compose -f deploy/docker-compose.yml up -d --build
# Anwendung: http://localhost:8000
```

### Was `bootstrap-env.sh` macht

`JWT_SECRET`, `CONFIG_ENCRYPTION_KEY` und `PG_PASSWORD` haben unterschiedliche
Formate (64-Hex vs. 44-Base64-Fernet vs. 32-Base64). Wer einen Wert im
falschen Format setzt — ein klassischer Fehler ist `openssl rand -hex 32` fuer
den Fernet-Key — landet in einem Crash-Loop, in dem der Backend-Container
beim Start abbricht und der Reverse-Proxy 502 liefert. Das Script:

1. Legt `deploy/.env` aus `.env.example` an, falls noch nicht vorhanden.
2. Erkennt jeden noch unveraenderten Platzhalter (`replace-with-...`,
   `replace-me-...`) und ersetzt ihn durch einen frisch erzeugten
   Zufallswert im jeweils richtigen Format.
3. Faesst bestehende Werte nicht an, kann also bei Updates wiederholt
   ausgefuehrt werden.

Voraussetzung: `bash`, `openssl` (auf jedem Linux-Host vorhanden). Kein
Python noetig.

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

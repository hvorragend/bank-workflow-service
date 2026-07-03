# Deployment-Stack

Zwei Compose-Dateien: `docker-compose.yml` ist der Prod-taugliche Basis-Stack
(Backend mit SQLite + Web mit React/Nginx). `docker-compose.dev.yml` ist ein
reines Dev-Override und ergänzt den Mail-Catcher **Mailpit** — der gehört
NICHT in Produktion (S-003). Der Basis-Stack verdrahtet bewusst keinen
Mail-Catcher als Prod-SMTP; der SMTP-Server wird im Admin-Panel konfiguriert.

## Schnellstart (Dev)

```bash
./deploy/dev-up.sh
```

Das Skript erzeugt beim ersten Lauf `deploy/.env` mit echten Secrets, startet
Basis-Stack **plus** Dev-Override (Mailpit), baut die Container und wartet auf
den Backend-Healthcheck.

Endpunkte nach dem Start:

- React-Frontend:   <http://localhost:8000>
- OpenAPI / Swagger: <http://localhost:8000/docs>
- Mailpit (Mail-UI): <http://localhost:8025>

Stoppen mit `./deploy/dev-down.sh` (Volumes bleiben), oder
`./deploy/dev-down.sh --volumes` für einen frischen Start.

Manuell mit Mail-Catcher:

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up -d --build
```

SMTP im Admin-Panel dann auf `host=mailpit`, `port=1025` stellen (beide
Container liegen im selben Compose-Netz).

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
# Prod (nur Basis-Stack, KEIN Mail-Catcher):
docker compose -f deploy/docker-compose.yml up -d --build
```

## Nebenläufigkeit: genau EIN Worker (S-007)

Der SLA-Eskalations-Scheduler (APScheduler) ist ein **In-Process-Singleton**:
Er läuft im Backend-Prozess und pollt periodisch nach überfälligen Anträgen.
Liefe der Service mit mehreren Workern, würde jeder Worker seinen eigenen
Scheduler starten — Folge wären **doppelte Eskalationen** (doppelte Mails,
doppelte Statuswechsel, doppelte Audit-Einträge).

Deshalb:

- Der Container startet uvicorn fest mit `--workers 1` (siehe
  `backend/Dockerfile`). **Nicht** erhöhen.
- **Nicht** horizontal skalieren: kein `docker compose up --scale backend=N`,
  keine zweite Backend-Replica hinter dem Proxy.
- Muss durchgesetzt mehr Durchsatz her, ist das eine Architektur-Änderung
  (externer Scheduler / Lock in der DB), keine Worker-Zahl.

## Production-Deployment auf Proxmox

Vorgesehen ist ein Single-Host-Setup auf einer Linux-VM unter Proxmox:

1. VM bereitstellen (Ubuntu 24.04 LTS empfohlen), Docker Engine installieren.
2. Repo pullen, `./deploy/bootstrap-env.sh` für Secret-Generierung ausführen
   (oder `deploy/.env` manuell mit produktiven Werten füllen).
3. `docker compose -f deploy/docker-compose.yml up -d --build`
   (ohne `docker-compose.dev.yml` — Mailpit bleibt draußen).
4. Reverse-Proxy / TLS davorschalten (z. B. Traefik oder nginx auf dem Host).

## Produktions-Härtung (S-009)

Vor dem ersten Prod-Go-Live abarbeiten. Die genannten Env-Variablen werden in
`deploy/.env` gesetzt und sind in `deploy/.env.example` dokumentiert.

- [ ] **TLS davor**: Reverse-Proxy (Traefik/nginx) mit gültigem Zertifikat.
      Der Web-Container ist an `127.0.0.1:8000` gebunden und darf nicht direkt
      aus dem Netz erreichbar sein.
- [ ] **`REFRESH_COOKIE_SECURE=true`** — Refresh-Cookie nur über HTTPS.
- [ ] **`CORS_ALLOW_ORIGINS`** auf die echte Frontend-Origin setzen
      (z. B. `https://workflow.example-bank.de`), niemals `*` mit Cookies.
- [ ] **Kein Mail-Catcher**: nur den Basis-Stack starten (ohne
      `docker-compose.dev.yml`), echtes SMTP im Admin-Panel konfigurieren
      (siehe unten).
- [ ] **`SEED_DEMO_DATA` NICHT setzen** — keine erfundenen „genehmigten"
      Anträge im revisionsrelevanten System.
- [ ] **`TRUST_PROXY_HEADERS`** nur setzen, wenn der Service NICHT mit
      `--proxy-headers` läuft. Der mitgelieferte Container startet uvicorn
      bereits mit `--proxy-headers --forwarded-allow-ips=*`, also normalerweise
      leer lassen. Setzen nur hinter einem vertrauenswürdigen Proxy — sonst
      kann ein Client die Audit-IP fälschen.
- [ ] **`JWT_SECRET` / `CONFIG_ENCRYPTION_KEY`** echt (kein `replace-...`),
      im richtigen Format.
- [ ] **`LOG_LEVEL`** auf `info` oder restriktiver.
- [ ] **Genau 1 Worker** (siehe Abschnitt oben) — nicht skalieren.
- [ ] **Backups testen**: mindestens einen Restore aus `sqlite_backup.sh` real
      durchspielen (siehe `docs/runbooks/backup_restore.md`).

### Echtes SMTP für Produktion

Kein Mail-Catcher in Prod. Statt Mailpit im Admin-Panel unter
System/Benachrichtigungen den produktiven Mailserver eintragen: Host, Port
(i. d. R. 587 STARTTLS oder 465 SMTPS), Absender, Benutzer/Passwort. Das
SMTP-Passwort wird mit `CONFIG_ENCRYPTION_KEY` verschlüsselt in der DB abgelegt.

## Backups (relevant für MaRisk AT 7.2 / DORA Art. 11)

- `backup/sqlite_backup.sh` — SQLite-Online-Snapshot via `sqlite3 .backup`
  (konsistent auch bei laufenden Schreibzugriffen, inkl. `integrity_check`;
  WAL-sicher — ein reiner `cp` wäre es nicht)
- `backup/storage_backup.sh` — `tar.gz` des Anhang-Volumes (löst den
  Volumenamen über die Docker-API auf, kein hartkodierter Host-Pfad)
- `backup/cron.example` — Beispiel-Crontab mit 30-Tage-Aufbewahrung
- Proxmox Backup Server für die VM-Ebene als zweites Standbein
- Restore-Tests gehören in die Notfalldokumentation
  (`docs/runbooks/backup_restore.md`)

## Reproduzierbarer Backend-Build (O-001)

Der Docker-Build installiert die Laufzeit-Dependencies aus dem Lockfile
`backend/requirements.lock` (exakt gepinnte Versionen inkl. transitiver Deps),
nicht aus den offenen Floors in `pyproject.toml`. Die App selbst wird danach
mit `--no-deps` installiert. So ist der Build byte-nah reproduzierbar.

Lockfile nach einem Dependency-Update neu erzeugen:

```bash
cd backend
python -m venv .venv && .venv/bin/pip install .   # Floors aufloesen
# Laufzeit-Closure einfrieren (ohne dev-Deps) und requirements.lock ersetzen.
# Basis-Image python:3.11.x-slim ebenfalls konservativ pinnen.
```

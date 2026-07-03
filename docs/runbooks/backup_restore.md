# Backup & Restore — Runbook

Operatives Runbook für die Volksbank Gronau-Ahaus eG. Zielsetzung: jeder
Routine-Backup-Lauf läuft automatisch, jeder Restore-Vorgang ist
nachvollziehbar dokumentiert (MaRisk AT 7.2 Tz. 5, DORA Art. 11).

## Architektur in zwei Sätzen

Es gibt drei zustandsbehaftete Bestandteile: die **SQLite-Datenbank**
(Anträge, Definitionen, Audit — eine Datei `/app/data/bank_workflow.db` im
Backend-Container, persistiert im Docker-Volume `bws-data`), das Storage-Volume
`bws-attachments` (hochgeladene Dateien) und die Konfigurationsdateien
(`config/users.json`, `config/ldap.toml`, `config/role_emails.toml`,
`deploy/.env`). Backups müssen alle drei abdecken.

> Hinweis WAL-Mode: Die DB läuft im WAL-Journal-Modus. Ein reiner `cp` der
> `.db`-Datei ist deshalb **nicht** konsistent — nicht eingecheckte
> Transaktionen liegen in `bank_workflow.db-wal`. Ein gültiger Snapshot
> entsteht nur über `sqlite3 .backup` (bzw. `VACUUM INTO`), genau das macht
> `deploy/backup/sqlite_backup.sh`. Beim Restore müssen die Seitendateien
> `-wal`/`-shm` mit beachtet werden (siehe unten).

## Backup-Frequenz

| Schicht | Cron | Skript | Aufbewahrung |
|---|---|---|---|
| SQLite-DB | täglich 02:00 UTC | `deploy/backup/sqlite_backup.sh` | 30 Tage am Host, 90 Tage auf Proxmox Backup Server |
| Storage-Volume | täglich 02:30 UTC | `deploy/backup/storage_backup.sh` | wie oben |
| Proxmox-VM-Snapshot | wöchentlich Sonntag 03:00 UTC | (Proxmox-eigen) | 8 Wochen |
| `config/`-Verzeichnis | bei jeder Änderung | (manuell, am besten in Git über internes Repo) | 1 Jahr |

Vorlage-Crontab: `deploy/backup/cron.example`. Übertragen via
`crontab /opt/bws/deploy/backup/cron.example` auf den Backup-Host.

Das Backup-Skript erzeugt den Snapshot mit `sqlite3 .backup` (Online-Backup-API,
konsistent auch bei laufenden Schreibzugriffen), prüft ihn mit
`PRAGMA integrity_check` und legt ihn als `bws-sqlite-<TS>.db` ab. Das
`sqlite3`-CLI ist dafür im Backend-Image installiert.

## Restore — SQLite

Die Wiederherstellung ersetzt die DB-Datei im Volume durch einen Backup-Stand.
Weil `.backup` einen bereits konsolidierten Snapshot liefert, wird **ohne**
`-wal`/`-shm`-Dateien zurückgespielt; eventuell noch vorhandene Alt-Dateien
`-wal`/`-shm` MÜSSEN entfernt werden, sonst mischt SQLite alten WAL-Inhalt in
den frischen Stand.

```bash
# 1. Backend stoppen (kein Schreibzugriff während des Austauschs)
docker compose -f deploy/docker-compose.yml stop backend

# 2. Backup-Datei in das Daten-Volume legen und die alte DB inkl. WAL-/SHM-
#    Seitendateien ersetzen. Wir fahren dazu kurz einen Wegwerf-Container hoch,
#    der nur das Volume gemountet hat (Backend läuft nicht).
BACKUP=/backups/bws-sqlite-2026-05-04T02-00-00Z.db

docker run --rm -v bws_bws-data:/data -v /backups:/backups:ro alpine:3.20 sh -c '
    rm -f /data/bank_workflow.db /data/bank_workflow.db-wal /data/bank_workflow.db-shm &&
    cp "'"$BACKUP"'" /data/bank_workflow.db
'

# 3. Migrationen sicherheitshalber anwenden (idempotent). Läuft in einem
#    Einweg-Backend-Container; DATABASE_URL kommt aus dem Compose-Env.
docker compose -f deploy/docker-compose.yml run --rm backend alembic upgrade head

# 4. Backend starten
docker compose -f deploy/docker-compose.yml start backend

# 5. Smoke-Test
curl -sf http://localhost:8000/health
```

> Volumename prüfen: Der tatsächliche Docker-Volumename setzt sich aus
> Compose-Projektname (`bws`) und Volume (`bws-data`) zusammen, also
> `bws_bws-data`. Mit `docker volume ls` verifizieren.

Anschließend in der Innenrevision protokollieren:

- Wer hat den Restore wann durchgeführt?
- Welcher Backup-Stempel wurde wiederhergestellt?
- Welcher Zeitraum ist potentiell verloren (zwischen Backup und Vorfall)?

## Restore — Datei-Anhänge

```bash
# 1. Backend stoppen (sonst können Files noch geschrieben werden)
docker compose -f deploy/docker-compose.yml stop backend

# 2. Volume leeren und Backup zurückspielen
docker volume rm bws_bws-attachments
docker volume create bws_bws-attachments
sudo tar -xzf /backups/bws-attachments-2026-05-04T02-30-00Z.tar.gz \
    -C /var/lib/docker/volumes/bws_bws-attachments/

# 3. Backend starten
docker compose -f deploy/docker-compose.yml start backend
```

Akzeptanzkriterium: ein bekannter Antrag mit Anhang lässt sich öffnen,
SHA-256 stimmt mit dem in der DB hinterlegten Hash überein.

## Restore — Konfiguration

`config/users.json`, `config/ldap.toml`, `config/role_emails.toml` und
`deploy/.env` aus dem internen Git-Repo bzw. Vault zurücklegen. Backend neu
starten, damit Settings frisch geladen werden:

```bash
docker compose -f deploy/docker-compose.yml restart backend
```

## JWT-Schlüsselrotation

Hintergrund: bei Verdacht auf Kompromittierung des `JWT_SECRET` muss er
gewechselt werden, ohne dass alle aktiven User-Sessions sofort verloren gehen.

1. Neuen Schlüssel erzeugen:
   ```bash
   NEW_KEY=$(openssl rand -hex 32)
   ```
2. In `deploy/.env` die Variable `JWT_SECRETS` setzen — neuestes Secret zuerst,
   das alte als zweites Element:
   ```
   JWT_SECRETS=<NEW_KEY>,<ALTES_SECRET>
   ```
3. Backend neu starten:
   ```bash
   docker compose -f deploy/docker-compose.yml restart backend
   ```
4. Nach Ablauf des längsten Refresh-Tokens (Default 8 Stunden) das alte Secret
   aus `JWT_SECRETS` entfernen, Backend erneut neu starten.
5. Im Audit-Log eintragen: wer, wann, warum (Verdacht / Routine).

`JWT_SECRET` (Singleton) bleibt aus Backwards-Compat-Gründen erhalten — wird
aber überschrieben, sobald `JWT_SECRETS` gesetzt ist.

## Restore-Übung (vierteljährlich)

Innenrevision plant einmal pro Quartal eine echte Übung mit einem ≥ 30 Tage
alten Backup. Schritte werden mit den Test-Cases in
`tests/test_notfall.py` (DR-1, DR-3) abgeglichen, Protokoll an die Innenrevision
und ans IT-Risiko-Management.

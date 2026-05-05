# Backup & Restore — Runbook

Operatives Runbook für die Volksbank Gronau-Ahaus eG. Zielsetzung: jeder
Routine-Backup-Lauf läuft automatisch, jeder Restore-Vorgang ist
nachvollziehbar dokumentiert (MaRisk AT 7.2 Tz. 5, DORA Art. 11).

## Architektur in zwei Sätzen

Es gibt drei zustandsbehaftete Bestandteile: die Postgres-Datenbank
(Anträge, Definitionen, Audit), das Storage-Volume `bws-attachments`
(hochgeladene Dateien) und die Konfigurationsdateien (`config/users.json`,
`config/ldap.toml`, `config/role_emails.toml`, `deploy/.env`). Backups
müssen alle drei abdecken.

## Backup-Frequenz

| Schicht | Cron | Skript | Aufbewahrung |
|---|---|---|---|
| Postgres-DB | täglich 02:00 UTC | `deploy/backup/pg_dump.sh` | 30 Tage am Host, 90 Tage auf Proxmox Backup Server |
| Storage-Volume | täglich 02:30 UTC | `deploy/backup/storage_backup.sh` | wie oben |
| Proxmox-VM-Snapshot | wöchentlich Sonntag 03:00 UTC | (Proxmox-eigen) | 8 Wochen |
| `config/`-Verzeichnis | bei jeder Änderung | (manuell, am besten in Git über internes Repo) | 1 Jahr |

Vorlage-Crontab: `deploy/backup/cron.example`. Übertragen via
`crontab /opt/bws/deploy/backup/cron.example` auf den Backup-Host.

## Restore — Postgres

```bash
# 1. Backend stoppen
docker compose -f deploy/docker-compose.yml stop backend

# 2. DB neu erstellen, alten Stand zurückspielen
docker compose -f deploy/docker-compose.yml exec postgres psql -U bws \
    -c "DROP DATABASE IF EXISTS bws;"
docker compose -f deploy/docker-compose.yml exec postgres psql -U bws \
    -c "CREATE DATABASE bws;"
docker compose -f deploy/docker-compose.yml exec -T postgres pg_restore \
    --clean --if-exists -U bws -d bws < /backups/bws-pg-2026-05-04T02-00-00Z.dump

# 3. Migrationen sicherheitshalber anwenden (idempotent)
docker compose -f deploy/docker-compose.yml run --rm backend alembic upgrade head

# 4. Backend starten
docker compose -f deploy/docker-compose.yml start backend

# 5. Smoke-Test
curl -sf http://localhost:8000/ready
```

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

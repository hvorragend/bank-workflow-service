#!/usr/bin/env bash
# SQLite-Backup fuer Bank Workflow Service.
#
# Aufruf aus der Cron-Tab des Hosts:
#   0 2 * * *  /opt/bws/deploy/backup/sqlite_backup.sh >> /var/log/bws-backup.log 2>&1
#
# Ergebnis: /backups/bws-sqlite-YYYY-MM-DDTHH-MM-SSZ.db
# Aufbewahrung wird hier nicht implementiert — uebernimmt entweder
# der find-Cron in cron.example, der Proxmox Backup Server oder ein Wrapper.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/bws/deploy}"

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="$BACKUP_DIR/bws-sqlite-$TS.db"

cd "$COMPOSE_DIR"

# `sqlite3 .backup` ist auch waehrend laufender Schreibzugriffe konsistent
# (interner Online-Backup-API von SQLite). Wir rufen es im Backend-Container
# auf, weil dort die DB-Datei und das sqlite3-Binary gemeinsam liegen.
docker compose exec -T backend sh -c "sqlite3 /app/data/bank_workflow.db \".backup '/tmp/snapshot.db'\" && cat /tmp/snapshot.db && rm /tmp/snapshot.db" > "$OUT"

# Permissions sperren — nur root und die Backup-Gruppe.
chmod 0640 "$OUT"
echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') backup_ok size=$(stat -c%s "$OUT") path=$OUT"

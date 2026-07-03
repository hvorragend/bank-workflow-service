#!/usr/bin/env bash
# SQLite-Backup fuer Bank Workflow Service.
#
# Aufruf aus der Cron-Tab des Hosts:
#   0 2 * * *  /opt/bws/deploy/backup/sqlite_backup.sh >> /var/log/bws-backup.log 2>&1
#
# Ergebnis: /backups/bws-sqlite-YYYY-MM-DDTHH-MM-SSZ.db
# Aufbewahrung wird hier nicht implementiert — uebernimmt entweder
# der find-Cron in cron.example, der Proxmox Backup Server oder ein Wrapper.
#
# WICHTIG (WAL-Mode ist aktiv): Ein reiner `cp` der .db-Datei waere INKONSISTENT,
# weil noch nicht eingecheckte Transaktionen im .db-wal liegen. `sqlite3 .backup`
# nutzt die Online-Backup-API von SQLite und erzeugt einen in sich konsistenten
# Snapshot inkl. WAL — auch waehrend laufender Schreibzugriffe. Das sqlite3-CLI
# ist im Backend-Image installiert (siehe backend/Dockerfile).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/bws/deploy}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
SERVICE="${SERVICE:-backend}"
DB_PATH="${DB_PATH:-/app/data/bank_workflow.db}"
# Snapshot-Ziel im Container-eigenen /tmp (nicht auf dem persistenten Volume).
SNAP_IN_CONTAINER="/tmp/bws-snapshot-$$.db"

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="$BACKUP_DIR/bws-sqlite-$TS.db"

cd "$COMPOSE_DIR"

dc() { docker compose -f "$COMPOSE_FILE" "$@"; }

# Aufraeumen des Container-Snapshots auch bei Fehler.
cleanup() { dc exec -T "$SERVICE" sh -c "rm -f '$SNAP_IN_CONTAINER'" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# 1. Konsistenten Online-Snapshot IM Container erzeugen (WAL-sicher).
dc exec -T "$SERVICE" sh -c "sqlite3 '$DB_PATH' \".backup '$SNAP_IN_CONTAINER'\""

# 2. Snapshot verifizieren, bevor er als gueltiges Backup gilt. Ein Backup, das
#    'ok' nicht bestaetigt, ist wertlos und darf keinen Erfolg vortaeuschen.
INTEGRITY="$(dc exec -T "$SERVICE" sh -c "sqlite3 '$SNAP_IN_CONTAINER' 'PRAGMA integrity_check;'" | tr -d '\r')"
if [ "$INTEGRITY" != "ok" ]; then
  echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') backup_FAILED integrity='$INTEGRITY'" >&2
  exit 1
fi

# 3. Snapshot als Datei aus dem Container holen (robuster als `cat` ueber stdout,
#    das bei jeder Byte-/Encoding-Stoerung ein korruptes Backup liefern koennte).
dc cp "$SERVICE:$SNAP_IN_CONTAINER" "$OUT"

# 4. Permissions sperren — nur root und die Backup-Gruppe.
chmod 0640 "$OUT"
echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') backup_ok integrity=ok size=$(stat -c%s "$OUT") path=$OUT"

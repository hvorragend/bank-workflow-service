#!/usr/bin/env bash
# pg_dump-Cron fuer Bank Workflow Service.
#
# Aufruf von der Cron-Tab des Hosts:
#   0 2 * * *  /opt/bws/deploy/backup/pg_dump.sh >> /var/log/bws-backup.log 2>&1
#
# Ergebnis: /backups/bws-pg-YYYY-MM-DD.dump
# Aufbewahrung wird hier nicht implementiert — uebernimmt entweder
# logrotate, der Proxmox Backup Server oder ein Wrapper-Skript.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/bws/deploy}"
PG_USER="${PG_USER:-bws}"
PG_DB="${PG_DB:-bws}"

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="$BACKUP_DIR/bws-pg-$TS.dump"

cd "$COMPOSE_DIR"
docker compose exec -T postgres pg_dump \
  --format=custom --compress=6 \
  -U "$PG_USER" -d "$PG_DB" > "$OUT"

# Permissions sperren — nur root und die Backup-Gruppe.
chmod 0640 "$OUT"
echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') backup_ok size=$(stat -c%s "$OUT") path=$OUT"

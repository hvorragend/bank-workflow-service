#!/usr/bin/env bash
# Datei-Anhaenge-Backup. Erzeugt ein tar.gz des Storage-Volumes auf dem Host.
#
# Cron:
#   30 2 * * *  /opt/bws/deploy/backup/storage_backup.sh >> /var/log/bws-backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
# bei docker-compose-Volumes liegt das echte Storage unter
# /var/lib/docker/volumes/<projekt>_bws-attachments/_data — Pfad auf dem Host.
STORAGE_PATH="${STORAGE_PATH:-/var/lib/docker/volumes/bws_bws-attachments/_data}"

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="$BACKUP_DIR/bws-attachments-$TS.tar.gz"

if [ ! -d "$STORAGE_PATH" ]; then
  echo "STORAGE_PATH existiert nicht: $STORAGE_PATH" >&2
  exit 1
fi

tar -czf "$OUT" -C "$(dirname "$STORAGE_PATH")" "$(basename "$STORAGE_PATH")"
chmod 0640 "$OUT"
echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') storage_backup_ok size=$(stat -c%s "$OUT") path=$OUT"

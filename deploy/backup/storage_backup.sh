#!/usr/bin/env bash
# Datei-Anhaenge-Backup. Erzeugt ein tar.gz des Storage-Volumes auf dem Host.
#
# Cron:
#   30 2 * * *  /opt/bws/deploy/backup/storage_backup.sh >> /var/log/bws-backup.log 2>&1
#
# F-024: Statt eines hartkodierten Host-Pfads unter /var/lib/docker/volumes/...
# (bricht bei anderem Compose-Projektnamen, rootless-Docker oder abweichendem
# Storage-Driver) wird das Volume ueber die Docker-API aufgeloest und der Inhalt
# aus einem Wegwerf-Container heraus getart. Der alte Pfad bleibt als
# STORAGE_PATH-Override moeglich.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
# Compose-Projektname (docker-compose.yml: `name: bws`) + Volume-Name ergeben
# den Docker-Volumenamen. Beide ueberschreibbar.
COMPOSE_PROJECT="${COMPOSE_PROJECT:-bws}"
VOLUME_NAME="${VOLUME_NAME:-${COMPOSE_PROJECT}_bws-attachments}"

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="$BACKUP_DIR/bws-attachments-$TS.tar.gz"

# Optionaler direkter Host-Pfad (Legacy-Verhalten). Wenn gesetzt, hat er Vorrang.
if [ -n "${STORAGE_PATH:-}" ]; then
  if [ ! -d "$STORAGE_PATH" ]; then
    echo "STORAGE_PATH existiert nicht: $STORAGE_PATH" >&2
    exit 1
  fi
  tar -czf "$OUT" -C "$(dirname "$STORAGE_PATH")" "$(basename "$STORAGE_PATH")"
else
  # Existenz des Volumes pruefen — klare Fehlermeldung statt leerem Tar.
  if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
    echo "Docker-Volume nicht gefunden: $VOLUME_NAME" >&2
    echo "Vorhandene Volumes:" >&2
    docker volume ls --format '  {{.Name}}' >&2 || true
    exit 1
  fi
  # tar.gz aus einem Wegwerf-Container, der das Volume read-only mountet.
  # Stream geht ueber stdout auf den Host — kein Zugriff auf interne Docker-Pfade noetig.
  docker run --rm -v "$VOLUME_NAME:/data:ro" alpine:3.20 \
    tar -czf - -C /data . > "$OUT"
fi

chmod 0640 "$OUT"
echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') storage_backup_ok size=$(stat -c%s "$OUT") path=$OUT"

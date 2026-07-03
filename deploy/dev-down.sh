#!/usr/bin/env bash
# Dev-Stack herunterfahren.
#
# Verwendung:
#   ./deploy/dev-down.sh                # Container stoppen, Volumes (SQLite-DB, Anhaenge) bleiben
#   ./deploy/dev-down.sh --volumes      # zusaetzlich Volumes loeschen (frischer Start beim naechsten Up)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
DEV_OVERRIDE="$SCRIPT_DIR/docker-compose.dev.yml"

EXTRA_ARGS=()
if [[ "${1:-}" == "--volumes" || "${1:-}" == "-v" ]]; then
    EXTRA_ARGS+=(--volumes)
    echo "==> Stoppe Stack UND loesche Volumes (SQLite-DB, Anhaenge gehen verloren)."
else
    echo "==> Stoppe Stack. Volumes bleiben erhalten — naechster ./dev-up.sh nimmt den DB-Stand wieder auf."
fi

docker compose -f "$COMPOSE_FILE" -f "$DEV_OVERRIDE" down "${EXTRA_ARGS[@]}"

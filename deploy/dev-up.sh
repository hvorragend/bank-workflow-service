#!/usr/bin/env bash
# Dev-Stack hochfahren: Bootstrap der .env (falls noetig), dann Komplett-Stack
# (Backend + Web + Mailpit-Mail-Catcher) via docker compose. Idempotent.
#
# Der Mail-Catcher (Mailpit) kommt bewusst aus dem Dev-Override
# docker-compose.dev.yml und ist NICHT Teil des Prod-Stacks (S-003).
#
# Verwendung:
#   ./deploy/dev-up.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
DEV_OVERRIDE="$SCRIPT_DIR/docker-compose.dev.yml"
ENV_FILE="$SCRIPT_DIR/.env"

# --- Vorbedingungen ---------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    echo "FEHLER: 'docker' ist nicht installiert. Siehe https://docs.docker.com/engine/install/" >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "FEHLER: 'docker compose' (V2-Plugin) ist nicht verfuegbar." >&2
    echo "       Auf aktuellen Distributionen via 'apt install docker-compose-plugin'." >&2
    exit 1
fi

# --- 1. .env vorbereiten ----------------------------------------------------

if [[ ! -f "$ENV_FILE" ]]; then
    echo "==> Keine deploy/.env gefunden — generiere Secrets via bootstrap-env.sh."
    "$SCRIPT_DIR/bootstrap-env.sh"
else
    echo "==> deploy/.env vorhanden — bestehende Secrets bleiben unangetastet."
fi

# --- 2. Stack starten -------------------------------------------------------

echo "==> Baue und starte Container (backend + web + mailpit) ..."
docker compose -f "$COMPOSE_FILE" -f "$DEV_OVERRIDE" up -d --build

# --- 3. Auf Backend-Healthcheck warten --------------------------------------

echo "==> Warte auf Backend-Bereitschaft auf http://localhost:8000/health ..."
deadline=$(( $(date +%s) + 60 ))
while true; do
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        echo "==> Backend antwortet."
        break
    fi
    if (( $(date +%s) >= deadline )); then
        echo "WARN: Backend antwortet nach 60s nicht. Logs pruefen mit:" >&2
        echo "      docker compose -f $COMPOSE_FILE logs backend" >&2
        exit 2
    fi
    sleep 2
done

# --- 4. Endpunkte ausgeben --------------------------------------------------

cat <<EOF

  Stack laeuft.

    Frontend (React):    http://localhost:8000
    OpenAPI / Swagger:   http://localhost:8000/docs
    Mailpit (Mail-UI):   http://localhost:8025

  Logs:        docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml logs -f
  Stoppen:     ./deploy/dev-down.sh
  Frontend-Hot-Reload: cd web && pnpm dev   (gegen das laufende Backend)

EOF

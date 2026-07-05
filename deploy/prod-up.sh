#!/usr/bin/env bash
# Prod-Stack hochfahren: Bootstrap der .env (falls noetig), dann NUR den
# Basis-Stack (Backend + Web) via docker compose — OHNE das Dev-Override,
# also ohne Mailpit-Mail-Catcher (S-003). Idempotent.
#
# Das Skript ersetzt die manuellen Schritte 2+3 aus deploy/README.md
# ("Production-Deployment auf Proxmox"). Reverse-Proxy/TLS davorschalten
# und die Checkliste "Produktions-Haertung" bleiben Aufgabe des Operators.
#
# Verwendung:
#   ./deploy/prod-up.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
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

# --- 2. Haertungs-Hinweise (nicht blockierend) -------------------------------
# Die Checkliste "Produktions-Haertung" in deploy/README.md bleibt massgeblich;
# hier nur die zwei Punkte, die man beim Go-Live am haeufigsten vergisst.

get_env_value() {
    grep -E "^${1}=" "$ENV_FILE" | head -n1 | cut -d= -f2- || true
}

if [[ "$(get_env_value REFRESH_COOKIE_SECURE)" != "true" ]]; then
    echo "WARN: REFRESH_COOKIE_SECURE ist nicht 'true' — fuer Prod hinter TLS setzen (deploy/.env)." >&2
fi
if [[ -n "$(get_env_value SEED_DEMO_DATA)" ]]; then
    echo "WARN: SEED_DEMO_DATA ist gesetzt — fiktive Demo-Antraege gehoeren NICHT in Produktion." >&2
fi

# --- 3. Stack starten (nur Basis, kein Mailpit) ------------------------------

echo "==> Baue und starte Container (backend + web) ..."
docker compose -f "$COMPOSE_FILE" up -d --build

# --- 4. Auf Backend-Healthcheck warten --------------------------------------

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

# --- 5. Endpunkte + naechste Schritte ausgeben -------------------------------

cat <<EOF

  Stack laeuft (Basis-Stack, ohne Mail-Catcher).

    Frontend (React):    http://localhost:8000
    OpenAPI / Swagger:   http://localhost:8000/docs

  Vor dem Go-Live: Checkliste "Produktions-Haertung" in deploy/README.md
  abarbeiten (TLS-Reverse-Proxy, WEB_HTTP_BIND=127.0.0.1, CORS, Backups, ...).

  Logs:        docker compose -f deploy/docker-compose.yml logs -f
  Stoppen:     docker compose -f deploy/docker-compose.yml down

EOF

# --- 6. Initial-Admin-Zugangsdaten anzeigen (nur bei Erstinbetriebnahme) -----
if creds="$(docker compose -f "$COMPOSE_FILE" exec -T backend \
        cat /app/data/initial-admin-password.txt 2>/dev/null)"; then
    cat <<EOF
  Erstinbetriebnahme — automatisch angelegter Admin-Login:

$(echo "$creds" | grep -E '^(username|password)=' | sed 's/^/    /')

  Nach dem ersten Login: Passwort im Admin-Panel aendern (die Datei
  /app/data/initial-admin-password.txt im Container danach loeschen).

EOF
fi

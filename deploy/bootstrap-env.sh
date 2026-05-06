#!/usr/bin/env bash
# Idempotenter Setup-Helfer fuer deploy/.env.
#
# Aufgaben:
#   1. Falls deploy/.env fehlt, aus deploy/.env.example anlegen.
#   2. Jede Zeile, deren Wert noch ein bekannter Platzhalter aus .env.example
#      ist (replace-with-..., replace-me-...), durch einen frisch generierten
#      Zufallswert im jeweils richtigen Format ersetzen:
#         JWT_SECRET            -> 64 Hex-Zeichen (openssl rand -hex 32)
#         CONFIG_ENCRYPTION_KEY -> 44 url-safe Base64 (Fernet-Format)
#         PG_PASSWORD           -> 32 url-safe Base64
#   3. Werte, die NICHT auf einem Platzhalter stehen, bleiben unangetastet —
#      das Script kann beliebig oft erneut ausgefuehrt werden, ohne bestehende
#      Geheimnisse zu ueberschreiben.
#
# Voraussetzungen: bash, sed, openssl. Kein Python, kein Docker noetig.
#
# Verwendung:
#   ./deploy/bootstrap-env.sh                    # standard-Pfad deploy/.env
#   ./deploy/bootstrap-env.sh /pfad/zur/.env     # alternativer Pfad
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${1:-$SCRIPT_DIR/.env}"
EXAMPLE_FILE="$SCRIPT_DIR/.env.example"

if ! command -v openssl >/dev/null 2>&1; then
    echo "FEHLER: 'openssl' ist nicht installiert. Bitte zuerst 'apt install openssl'." >&2
    exit 1
fi

if [[ ! -f "$EXAMPLE_FILE" ]]; then
    echo "FEHLER: Beispieldatei nicht gefunden: $EXAMPLE_FILE" >&2
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Lege $ENV_FILE aus $EXAMPLE_FILE an."
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

# 64 Hex-Zeichen fuer JWT_SECRET (Format laut auth/config.py).
gen_hex32() {
    openssl rand -hex 32
}

# 44 url-safe Base64 fuer Fernet (Format laut security/secrets.py).
# openssl rand -base64 32 liefert "+/"-Variante; Fernet erwartet "-_". Padding
# mit '=' ist immer vorhanden (32 Bytes -> 44 Zeichen).
gen_fernet() {
    openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
}

# 32 url-safe Base64 fuer Postgres-Passwort. Keine Sonderzeichen, die in der
# DSN gequotet werden muessten.
gen_pg_pw() {
    openssl rand -base64 24 | tr '+/' '-_' | tr -d '=\n'
}

# Bekannte Platzhalter aus .env.example -> erwartete Generator-Funktion.
# Wer einen weiteren Platzhalter ergaenzt, muss ihn hier UND in
# app/security/secrets.py:_PLACEHOLDER_VALUES registrieren.
declare -A PLACEHOLDERS=(
    [JWT_SECRET]="replace-with-openssl-rand-hex-32"
    [CONFIG_ENCRYPTION_KEY]="replace-with-fernet-generate-key-output"
    [PG_PASSWORD]="replace-me-in-production"
)
declare -A GENERATORS=(
    [JWT_SECRET]="gen_hex32"
    [CONFIG_ENCRYPTION_KEY]="gen_fernet"
    [PG_PASSWORD]="gen_pg_pw"
)

replaced_any=0
for var in "${!PLACEHOLDERS[@]}"; do
    placeholder="${PLACEHOLDERS[$var]}"
    current="$(grep -E "^${var}=" "$ENV_FILE" || true)"
    if [[ -z "$current" ]]; then
        echo "WARN:  $var fehlt in $ENV_FILE — bitte aus $EXAMPLE_FILE ergaenzen."
        continue
    fi
    current_value="${current#${var}=}"
    if [[ "$current_value" != "$placeholder" ]]; then
        echo "OK:    $var ist bereits gesetzt — bleibt unveraendert."
        continue
    fi
    new_value="$(${GENERATORS[$var]})"
    # sed -i mit Trennzeichen '|', falls der generierte Wert '/' enthaelt.
    # Backslashes/&-Zeichen kommen aus den Generatoren oben nicht vor.
    sed -i "s|^${var}=.*|${var}=${new_value}|" "$ENV_FILE"
    echo "SET:   $var generiert (${#new_value} Zeichen)."
    replaced_any=1
done

chmod 600 "$ENV_FILE"

if [[ $replaced_any -eq 0 ]]; then
    echo
    echo "Nichts zu tun — alle Pflicht-Werte in $ENV_FILE sind bereits gesetzt."
else
    echo
    echo "Fertig. Naechster Schritt:"
    echo "  cd $SCRIPT_DIR && docker compose up -d --force-recreate backend"
fi

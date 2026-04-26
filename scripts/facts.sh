#!/usr/bin/env bash
# Uso: ./scripts/facts.sh <caso_id> [tipo] [soggetto]
# Esempi:
#   ./scripts/facts.sh caso_001
#   ./scripts/facts.sh caso_001 scadenza
#   ./scripts/facts.sh caso_001 diagnosi bambino

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

CASO_ID="${1:?Argomento 1 richiesto: caso_id (es: caso_001)}"
TIPO="${2:-}"
SOGGETTO="${3:-}"

TIPO_ARG=""
if [[ -n "${TIPO}" ]]; then
    TIPO_ARG="--tipo ${TIPO}"
fi

SOGGETTO_ARG=""
if [[ -n "${SOGGETTO}" ]]; then
    SOGGETTO_ARG="--soggetto ${SOGGETTO}"
fi

docker compose run --rm --entrypoint python3 ingestion \
    -m ingestion.facts \
    --caso-id "${CASO_ID}" \
    ${TIPO_ARG} \
    ${SOGGETTO_ARG}

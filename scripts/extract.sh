#!/usr/bin/env bash
# Uso: ./scripts/extract.sh <caso_id> [--dry-run]
# Esempio: ./scripts/extract.sh caso_001
#
# Richiede Ollama in esecuzione (avviato da ask.sh o manualmente).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

CASO_ID="${1:?Argomento 1 richiesto: caso_id (es: caso_001)}"
DRY_RUN="${2:-}"

DRY_RUN_ARG=""
if [[ "${DRY_RUN}" == "--dry-run" ]]; then
    DRY_RUN_ARG="--dry-run"
fi

if ! docker compose ps ollama | grep -q "running"; then
    echo "Avvio Ollama..."
    docker compose up -d ollama
    until docker compose exec ollama ollama list > /dev/null 2>&1; do
        sleep 2
    done
fi

echo "Estrazione fatti strutturati per caso '${CASO_ID}'..."
echo ""

docker compose run --rm --entrypoint python3 ingestion \
    -m ingestion.extract \
    --caso-id "${CASO_ID}" \
    ${DRY_RUN_ARG}

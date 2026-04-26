#!/usr/bin/env bash
# Uso:
#   Cartella caso (modo consigliato):
#     ./scripts/ingest.sh data/raw_docs/caso_001/
#     → caso_id = "caso_001" (dal nome cartella), tipo_atto dal nome file
#
#   File singolo:
#     ./scripts/ingest.sh data/raw_docs/perizia.txt caso_001 perizia

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

INPUT_ARG="${1:?Argomento 1 richiesto: path cartella caso o file singolo}"
DATA_DIR="${PROJECT_ROOT}/data"

# Risolvi path assoluto
if [[ "${INPUT_ARG}" = /* ]]; then
    INPUT_ABS="${INPUT_ARG}"
else
    INPUT_ABS="${PROJECT_ROOT}/${INPUT_ARG}"
fi

# Ricava tipo_atto dal nome file (primo token prima di _ o .)
# perizia_psicologica.txt → perizia
# verbale_udienza.txt     → verbale
# qualsiasi altro         → documento
# .json                   → ignorato (ingest.py rileva trascrizione in automatico)
guess_tipo() {
    local name
    name="${1,,}"  # lowercase
    for tipo in perizia verbale relazione atto consulenza sentenza ordinanza; do
        if [[ "$name" == ${tipo}* ]]; then
            echo "$tipo"
            return
        fi
    done
    echo "documento"
}

# Indicizza un singolo file
ingest_file() {
    local file_abs="$1"
    local caso_id="$2"
    local tipo_atto="$3"

    if [[ "${file_abs}" != "${DATA_DIR}"/* ]]; then
        echo "ERRORE: il file deve trovarsi dentro ${DATA_DIR}/" >&2
        exit 1
    fi

    local file_in_container="/data/${file_abs#${DATA_DIR}/}"

    echo "  Indicizzando: $(basename "${file_abs}")  [${tipo_atto}]"

    docker compose run --rm ingestion \
        --input "${file_in_container}" \
        --caso-id "${caso_id}" \
        --tipo-atto "${tipo_atto}"
}

if [[ -d "${INPUT_ABS}" ]]; then
    # ── Modalità cartella ──────────────────────────────────────
    CASO_ID="${2:-$(basename "${INPUT_ABS}")}"

    echo "Caso:     ${CASO_ID}"
    echo "Cartella: ${INPUT_ABS}"
    echo ""

    count=0
    for file in "${INPUT_ABS}"/*; do
        [[ -f "$file" ]] || continue
        TIPO=$(guess_tipo "$(basename "$file")")
        ingest_file "$file" "${CASO_ID}" "${TIPO}"
        ((count++)) || true
    done

    echo ""
    echo "Completato: ${count} file indicizzati per caso '${CASO_ID}'"

else
    # ── Modalità file singolo ──────────────────────────────────
    if [[ ! -f "${INPUT_ABS}" ]]; then
        echo "ERRORE: file non trovato: ${INPUT_ABS}" >&2
        exit 1
    fi

    CASO_ID="${2:?Modalita file singolo: argomento 2 richiesto (caso_id)}"
    TIPO_ATTO="${3:-$(guess_tipo "$(basename "${INPUT_ABS}")")}"

    echo "Caso: ${CASO_ID}"
    echo "Tipo: ${TIPO_ATTO}"
    echo ""

    ingest_file "${INPUT_ABS}" "${CASO_ID}" "${TIPO_ATTO}"

    echo ""
    echo "Completato."
fi

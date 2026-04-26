"""
extract.py — Estrazione fatti strutturati da chunk indicizzati → SQLite.

Uso:
    python3 -m ingestion.extract --caso-id caso_001
    python3 -m ingestion.extract --caso-id caso_001 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
from pathlib import Path

import requests

log = logging.getLogger(__name__)

OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://ollama:11434")
LLM_MODEL   = os.environ.get("LLM_MODEL",  "qwen2.5:7b-instruct-q4_K_M")
CHROMA_PATH = os.environ.get("CHROMA_PATH", "/indexes/chroma")
FACTS_DB    = os.environ.get("FACTS_DB",    "/indexes/facts.db")

TIPI_VALIDI = {
    "affermazione", "negazione", "ammissione", "opinione",
    "scadenza", "raccomandazione", "diagnosi", "terapia",
}


# ── SQLite ────────────────────────────────────────────────────

def _init_db(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS fatti (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            caso_id     TEXT NOT NULL,
            doc_id      TEXT NOT NULL,
            chunk_id    TEXT,
            tipo        TEXT,
            soggetto    TEXT,
            fatto       TEXT NOT NULL,
            data_evento TEXT,
            fonte_tipo  TEXT,
            contesto    TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_caso ON fatti(caso_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_tipo ON fatti(tipo, caso_id)")
    con.commit()
    return con


def _delete_existing(con: sqlite3.Connection, caso_id: str, chunk_id: str) -> None:
    con.execute(
        "DELETE FROM fatti WHERE caso_id = ? AND chunk_id = ?",
        (caso_id, chunk_id),
    )


def _insert_fatti(con: sqlite3.Connection, caso_id: str, chunk_id: str,
                  doc_id: str, fonte_tipo: str, contesto: str,
                  fatti: list[dict]) -> int:
    rows = []
    for f in fatti:
        tipo = f.get("tipo", "affermazione").lower()
        if tipo not in TIPI_VALIDI:
            tipo = "affermazione"
        rows.append((
            caso_id,
            doc_id,
            chunk_id,
            tipo,
            f.get("soggetto"),
            f.get("fatto", ""),
            f.get("data"),
            fonte_tipo,
            contesto[:500],
        ))
    if rows:
        con.executemany("""
            INSERT INTO fatti
                (caso_id, doc_id, chunk_id, tipo, soggetto, fatto, data_evento, fonte_tipo, contesto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        con.commit()
    return len(rows)


# ── Prompt + Ollama ───────────────────────────────────────────

_PROMPT_TEMPLATE = """\
Sei un assistente specializzato in analisi di documenti legali e forensi italiani.
Estrai tutti i fatti atomici dal testo seguente e restituisci SOLO un array JSON valido, senza testo aggiuntivo.

Tipi validi: affermazione, negazione, ammissione, opinione, scadenza, raccomandazione, diagnosi, terapia

Formato output (array JSON):
[
  {{"tipo": "scadenza", "soggetto": "padre", "fatto": "avviare parent training", "data": "entro 30 giorni dall'udienza"}},
  {{"tipo": "diagnosi", "soggetto": "bambino", "fatto": "DSA diagnosticato", "data": "marzo 2024"}}
]

Se non ci sono fatti rilevanti restituisci: []

Documento: {fonte_tipo} — {doc_id}
Testo:
{testo}

Array JSON:"""


def _call_ollama(prompt: str) -> str:
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 512},
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


def _parse_json(raw: str) -> list[dict]:
    # Estrai il primo array JSON dalla risposta
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group())
        return [f for f in data if isinstance(f, dict) and f.get("fatto")]
    except json.JSONDecodeError:
        return []


# ── Estrazione su un caso ─────────────────────────────────────

def extract(caso_id: str, dry_run: bool = False) -> None:
    import chromadb

    client     = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection("caso_corrente")

    result = collection.get(
        where={"caso_id": caso_id},
        include=["documents", "metadatas"],
    )

    if not result["ids"]:
        print(f"Nessun chunk trovato per caso '{caso_id}'.")
        return

    total_chunks = len(result["ids"])
    print(f"Caso '{caso_id}': {total_chunks} chunk da elaborare.\n")

    if dry_run:
        print("[dry-run] Nessuna scrittura su DB.\n")

    con = None if dry_run else _init_db(FACTS_DB)
    total_fatti = 0

    for chunk_id, testo, meta in zip(result["ids"], result["documents"], result["metadatas"]):
        doc_id     = meta.get("doc_id", "?")
        fonte_tipo = meta.get("tipo_atto", "documento")

        prompt = _PROMPT_TEMPLATE.format(
            fonte_tipo=fonte_tipo,
            doc_id=doc_id,
            testo=testo,
        )

        log.info(f"Elaboro chunk {chunk_id}...")
        raw   = _call_ollama(prompt)
        fatti = _parse_json(raw)

        if dry_run:
            print(f"[{chunk_id}] {doc_id} → {len(fatti)} fatti")
            for f in fatti:
                print(f"  [{f.get('tipo','?')}] {f.get('soggetto','?')}: {f.get('fatto','')}")
            print()
        else:
            _delete_existing(con, caso_id, chunk_id)
            n = _insert_fatti(con, caso_id, chunk_id, doc_id, fonte_tipo, testo, fatti)
            total_fatti += n
            print(f"  {chunk_id}: {n} fatti estratti")

    if not dry_run:
        con.close()
        print(f"\nCompletato: {total_fatti} fatti salvati in {FACTS_DB}")


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    p = argparse.ArgumentParser(description="Estrai fatti strutturati da un caso → SQLite")
    p.add_argument("--caso-id", required=True, help="ID caso (es: caso_001)")
    p.add_argument("--dry-run", action="store_true", help="Mostra i fatti senza salvare")
    args = p.parse_args()

    extract(args.caso_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

"""
facts.py — Interroga il database SQLite dei fatti strutturati.

Uso:
    python3 -m ingestion.facts --caso-id caso_001
    python3 -m ingestion.facts --caso-id caso_001 --tipo scadenza
    python3 -m ingestion.facts --caso-id caso_001 --soggetto padre
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

FACTS_DB = os.environ.get("FACTS_DB", "/indexes/facts.db")

TIPO_LABELS = {
    "affermazione":   "Affermazione",
    "negazione":      "Negazione",
    "ammissione":     "Ammissione",
    "opinione":       "Opinione",
    "scadenza":       "Scadenza",
    "raccomandazione":"Raccomandazione",
    "diagnosi":       "Diagnosi",
    "terapia":        "Terapia",
}


def query_fatti(
    caso_id:  str,
    tipo:     str | None = None,
    soggetto: str | None = None,
) -> list[dict]:
    if not Path(FACTS_DB).exists():
        return []

    con = sqlite3.connect(FACTS_DB)
    con.row_factory = sqlite3.Row

    sql    = "SELECT * FROM fatti WHERE caso_id = ?"
    params = [caso_id]

    if tipo:
        sql += " AND tipo = ?"
        params.append(tipo.lower())
    if soggetto:
        sql += " AND soggetto LIKE ?"
        params.append(f"%{soggetto}%")

    sql += " ORDER BY tipo, doc_id, id"

    rows = con.execute(sql, params).fetchall()
    con.close()
    return [dict(r) for r in rows]


def print_fatti(rows: list[dict]) -> None:
    if not rows:
        print("Nessun fatto trovato.")
        return

    # Raggruppa per tipo
    per_tipo: dict[str, list[dict]] = {}
    for r in rows:
        per_tipo.setdefault(r["tipo"], []).append(r)

    for tipo, gruppo in per_tipo.items():
        label = TIPO_LABELS.get(tipo, tipo.capitalize())
        print(f"\n{'─'*60}")
        print(f"  {label.upper()} ({len(gruppo)})")
        print(f"{'─'*60}")
        for f in gruppo:
            soggetto = f["soggetto"] or "?"
            data     = f"  [{f['data_evento']}]" if f.get("data_evento") else ""
            fonte    = f"{f['fonte_tipo']}: {f['doc_id']}"
            print(f"  • {soggetto}: {f['fatto']}{data}")
            print(f"    ↳ {fonte}")
    print()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    p = argparse.ArgumentParser(description="Interroga i fatti strutturati di un caso")
    p.add_argument("--caso-id",  required=True)
    p.add_argument("--tipo",     default=None,
                   help="Filtra per tipo: scadenza, diagnosi, terapia, ecc.")
    p.add_argument("--soggetto", default=None,
                   help="Filtra per soggetto (es: padre, madre, bambino)")
    args = p.parse_args()

    rows = query_fatti(args.caso_id, tipo=args.tipo, soggetto=args.soggetto)

    print(f"\n{'='*60}")
    print(f"  Caso: {args.caso_id}" +
          (f"  |  tipo: {args.tipo}" if args.tipo else "") +
          (f"  |  soggetto: {args.soggetto}" if args.soggetto else ""))
    print(f"  Totale: {len(rows)} fatti")
    print(f"{'='*60}")

    print_fatti(rows)


if __name__ == "__main__":
    main()

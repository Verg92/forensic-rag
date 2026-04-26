# CLAUDE.md — Forensic RAG

## Contesto progetto
Sistema RAG locale per studio legale (psicologia forense + avvocatura). Privacy-first, tutto in Docker, niente cloud per dati sensibili. Dettaglio completo in PROJECT_CONTEXT.md.

## Regole comunicative
- Usare sempre "tu" (mai "lei")
- Italiano in tutte le risposte

## Hardware
- OS: Windows + WSL2 (kernel microsoft-standard-WSL2)
- GPU: NVIDIA GTX 1050 Ti — CUDA via WSL2 passthrough
- Docker Desktop su Windows

## Stato attuale — Fase 2 quasi completa

### Cosa funziona già
- **Pipeline trascrizione**: `scripts/transcribe.sh` → whisper + pyannote → JSON in `data/transcripts/`
- **Ingestion**: `scripts/ingest.sh` → chunker + BGE-M3 (CPU) → ChromaDB + BM25 in `indexes/`
- **Retrieval ibrido**: `scripts/query.sh` → cerca su ChromaDB (semantico) + BM25 (keyword) → top-k chunk con score
- **87 chunk indicizzati** in `indexes/chroma/` e `indexes/bm25/index.pkl` (caso_001: perizia_psicologica, verbale_udienza, relazione, test.json)

### Prossimo step — da completare
**Integrare Ollama + Qwen 2.5 3B** per chiudere il loop RAG (retrieval → LLM → risposta con citazioni).

Il codice è già scritto e pronto:
- `src/ingestion/ask.py` — retrieval + chiamata Ollama HTTP + output con citazioni
- `scripts/ask.sh` — avvia Ollama, scarica il modello se assente, lancia ask.py
- `docker-compose.yml` — servizio `ollama` già configurato con GPU

**Da fare per testarlo:**
```bash
cd ~/forensic-rag
./scripts/ask.sh "Il padre ha fatto il parent training?" caso_001
```

La prima volta scarica Ollama (~1GB) e Qwen 3B (~2GB). Poi rimane in cache in `models/ollama/`.

Se funziona, il sistema risponde in italiano con citazioni tipo:
> "Il padre non ha partecipato ad alcun percorso di parent training [FONTE 1]..."
> [1] Perizia: perizia_psicologica (score 0.0142)

### Possibili problemi noti
- **Ollama non parte**: verificare che Docker Desktop sia in esecuzione e che la GPU sia visibile
- **Modello non trovato**: `docker compose exec ollama ollama pull qwen2.5:3b-instruct-q4_K_M`
- **Risposta lenta**: normale sulla 1050 Ti, CPU offload parziale — 3B è già il modello più piccolo ragionevole

## Struttura container Docker
| Container | Immagine | Uso |
|---|---|---|
| `whisper` | `forensic-rag/whisper:cuda` | trascrizione audio/video |
| `ingestion` | `forensic-rag/ingestion:cpu` | chunking + embedding + retrieval + ask |
| `ollama` | `ollama/ollama:latest` | LLM locale Qwen 3B |

Tutti con `profiles: [tools]` — si avviano solo con `docker compose run` o `docker compose up`.

## Variabili .env
```
GPU_BACKEND=cuda
HF_TOKEN=hf_...
LLM_MODEL=qwen2.5:3b-instruct-q4_K_M
```

## File chiave
| File | Scopo |
|---|---|
| `src/ingestion/ask.py` | RAG completo: retrieval → prompt → Ollama → risposta |
| `src/ingestion/retrieval.py` | Ricerca ibrida ChromaDB + BM25 |
| `src/ingestion/ingest.py` | Ingestion: chunk → embed → ChromaDB + BM25 |
| `src/ingestion/chunker_doc.py` | Chunker per TXT/PDF/DOCX |
| `src/ingestion/chunker_transcript.py` | Chunker per JSON trascrizioni |
| `src/transcription/pipeline.py` | Pipeline whisper + pyannote |
| `docs/guida_trascrizione.md` | Guida operativa completa (trascrizione + ingestion + query) |
| `PROJECT_CONTEXT.md` | Architettura, decisioni, piano fasi |

## Fasi del progetto
- ✅ Fase 0 — Setup (WSL2 + CUDA + Docker)
- ✅ Fase 1 — Pipeline trascrizione
- 🔄 Fase 2 — Indice caso corrente (manca solo test Ollama)
- ⬜ Fase 3 — Estrazione fatti strutturati (SQLite)
- ⬜ Fase 4 — Indici normativa + giurisprudenza
- ⬜ Fase 5 — Router multi-indice
- ⬜ Fase 6 — UI Streamlit

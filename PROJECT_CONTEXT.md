# Progetto RAG Forense — Contesto per continuità tra chat

## Obiettivo del progetto

Costruire un sistema di supporto AI per uno studio legale singolo (psicologia forense + avvocatura) che:

1. Trascriva fedelmente registrazioni di udienze/testimonianze con diarizzazione (chi dice cosa, quando)
2. Indicizzi documenti di casi (atti, perizie, verbali) + corpus normativo (codici, leggi) + corpus giurisprudenziale (sentenze)
3. Permetta di interrogare tutto il materiale con risposte che citano sempre le fonti in modo verificabile
4. Identifichi contraddizioni nelle testimonianze, analogie con casi precedenti, riferimenti normativi pertinenti

Volume previsto: ~20 ore/mese di audio da trascrivere, studio singolo.

## Principi architetturali (decisi e non negoziabili)

**Privacy-first con architettura ibrida futura.** Per ora tutto in locale. In produzione si adotterà modello ibrido con tre zone di dato:

- **Zona Rossa** (mai esce dal perimetro): audio originale, trascrizioni complete con nomi, documenti dei casi, embedding del contenuto sensibile, mappa di anonimizzazione
- **Zona Gialla** (locale → cloud solo dopo anonimizzazione seria): pattern astratti, query verso corpus pubblico, prompt di sintesi complessa
- **Zona Verde** (cloud libero): corpus legale pubblico, modelli pre-addestrati, ricerche web giuridiche

**Tutto in Docker, niente installazioni native.** Host ha solo driver GPU. Stack applicativo tutto in container. Questo abilita migrazione facile AMD → NVIDIA futura.

**Doppio backend GPU fin dall'inizio.** Dockerfile parametrizzati con `ARG GPU_BACKEND=rocm|cuda`. `.env` con config GPU-dipendente separata dal codice. Migrazione futura a NVIDIA = cambio variabile + rebuild, non riscrittura.

**Compliance.** Dati di natura penale = art. 10 GDPR + D.Lgs. 51/2018. Segreto professionale avvocato. AI Act EU come framework. Nessun transito su server USA non controllati. Scelta strumenti come Plaud rigettata per questo motivo (server USA, LLM di terzi nella pipeline).

## Hardware attuale (prototipo)

- **CPU:** AMD Ryzen 7 7700 (8C/16T, Zen 4)
- **GPU:** AMD Radeon RX 9060 XT 16GB VRAM (gfx1200, RDNA 4) — Device 0 in ROCm
- **iGPU:** AMD Ryzen integrated (gfx1036) — Device 1, ignorata (usare `HIP_VISIBLE_DEVICES=0`)
- **OS:** Ubuntu 24.04 LTS (dual boot su SSD dedicato)
- **Kernel:** 6.8+
- **Motherboard:** Gigabyte B650M AORUS ELITE AX ICE

## Hardware futuro (produzione)

Opzione ibrida concordata:
- PC locale modesto in studio per task continuativi (WhisperX, embedder, LLM piccolo) — budget ~4.000€
- Cloud GPU EU on-demand per task pesanti su dato anonimizzato (Scaleway L40S o simile) — ~50-200€/mese stimati
- **Probabile GPU futura: NVIDIA**, quindi architettura già predisposta per migrazione CUDA

## Stack tecnico deciso

| Livello | Componente | Scelta |
|---|---|---|
| OS | Ubuntu 24.04 LTS | ✅ installato |
| Driver GPU | ROCm 7.2.2 (no-dkms, kernel mainline) | ✅ installato |
| Container | Docker + Docker Compose | ✅ installato |
| LLM runtime | Ollama con backend ROCm | da fare |
| LLM principale | Qwen 2.5 7B Instruct Q4_K_M (multilingua, buon italiano) | da fare |
| ASR | WhisperX (large-v3) con backend ROCm | da fare |
| Diarizzazione | pyannote.audio 3.x | da fare |
| Embeddings | BGE-M3 (multilingua, ottimo italiano) via sentence-transformers | da fare |
| Reranker | bge-reranker-v2-m3 | da fare |
| Vector DB | ChromaDB persistente | da fare |
| Keyword search | rank_bm25 (libreria Python) | da fare |
| Fact extraction DB | SQLite | da fare |
| Framework RAG | LlamaIndex (preferito a LangChain per RAG puro) | da fare |
| Backend API | FastAPI | da fare |
| Frontend UI | Streamlit (per prototipo) | da fare |

## Architettura RAG — tre indici separati + router

**Indice A — Corpus normativo** (codici, leggi, decreti)
- Chunking: per articolo+comma (mai split per token)
- Metadati: `fonte`, `articolo`, `comma`, `data_vigenza`, `abrogato`
- Ricerca: BM25 70% + semantic 30%

**Indice B — Corpus giurisprudenziale** (Cassazione, Corte Cost., merito)
- Chunking: per massima + per punto di motivazione
- Metadati: `corte`, `sezione`, `numero_sentenza`, `data`, `materia`, `articoli_richiamati`, `tag_concettuali`
- Ricerca: semantic 60% + keyword 40% + filtri materia

**Indice C — Caso corrente** (atti, perizie, verbali, trascrizioni)
- Chunking: per turno di parola (audio) o per sezione/paragrafo (atti)
- Metadati: `caso_id`, `documento_id`, `tipo_atto`, `data_evento`, `parti_coinvolte`, `udienza_n`, `pagina`, `speaker`, `timestamp`
- Ricerca: ibrida bilanciata + filtri temporali rigorosi

**Router di query** (sopra i tre indici)
- LLM piccolo (Qwen 7B locale) classifica la domanda e la decompone in sub-query
- Decide quale indice/indici interrogare e con quali filtri
- Produce piano d'esecuzione strutturato

**Estrazione fatti strutturati** (livello extra sopra il RAG)
- Al momento dell'ingestione, LLM estrae da ogni chunk di testimonianza: `afferma_fatti`, `esprime_opinioni`, `ammissioni`, `negazioni` in JSON
- Salvato in SQLite relazionale accanto agli indici vettoriali
- Abilita query strutturate (cronologie, contraddizioni) che il pure RAG non sa fare

## Flusso a runtime (query)

1. Router classifica/decompone domanda
2. Esecutore lancia sub-query su indici giusti con filtri
3. Reranker (bge-reranker-v2-m3) riordina
4. Aggregatore unisce contesti, dedup, ordina
5. Sintetizzatore (LLM) produce risposta con `{claim, source_id, quote}`
6. Verificatore controlla che ogni quote esista davvero nei chunk
7. Formatter presenta con citazioni cliccabili

## Piano a fasi (stato aggiornato)

### ✅ Fase 0 — Setup sistema (COMPLETATA)

- [x] Ubuntu 24.04 LTS installato in dual boot
- [x] Apt update/upgrade + pacchetti base
- [x] ROCm 7.2.2 installato (via `amdgpu-install --usecase=rocm --no-dkms`, senza `graphics`)
  - Gotcha risolto: il repo `graphics/7.2.2` non esiste per ROCm 7.2.2, l'installer lo aggiungeva in `rocm.list`. Rimosso con `sed -i '/graphics\/7.2.2/d' /etc/apt/sources.list.d/rocm.list`
- [x] Utente nei gruppi `render, video`
- [x] Riavvio effettuato
- [x] Verifica: `rocminfo` mostra gfx1200, `rocm-smi` mostra GPU sana
- [x] Docker + Docker Compose installati
- [x] Test `docker run --rm --device=/dev/kfd --device=/dev/dri ... rocminfo` OK
- [x] Python venv in `~/forensic-rag/.venv`
- [x] Struttura cartelle progetto creata
- [x] PyTorch ROCm testato sull'host: `torch.cuda.is_available() == True`, matmul GPU OK

### 🔜 Fase 1 — Pipeline di trascrizione (PROSSIMA)

Obiettivo: WhisperX + pyannote in container Docker, input audio italiano multi-speaker, output JSON strutturato `{speaker, start, end, text}`.

**Da fare:**
- [ ] Dockerfile per container whisper con backend ROCm
- [ ] Test con audio pubblico italiano (es. audizione parlamentare, 5-10 min)
- [ ] Verifica qualità trascrizione (target WER < 5% su audio pulito)
- [ ] Verifica qualità diarizzazione (speaker identificati correttamente)
- [ ] Script helper per mappare `SPEAKER_00` → nomi reali
- [ ] Test su audio più lungo (1 ora) con 2-4 speaker
- [ ] Output JSON strutturato salvato in `data/transcripts/`

**Caveat noti:**
- `faster-whisper` (CTranslate2) su ROCm è acerbo. Piani B: `openai-whisper` puro con PyTorch+ROCm, o `whisper.cpp` con HIPBLAS (ROCm ufficiale, più stabile su AMD)
- `HIP_VISIBLE_DEVICES=0` obbligatorio per escludere iGPU
- Possibile `HSA_OVERRIDE_GFX_VERSION=12.0.0` se PyTorch non riconosce gfx1200

### Fase 2 — Indice caso corrente

Solo indice C prima. Chunker per trascrizioni e atti, metadati ricchi, ChromaDB+BM25, retrieval semplice. Test su caso finto.

### Fase 3 — Estrazione fatti strutturati

SQLite + prompt LLM per estrarre fatti atomici durante ingestione. Query SQL per cronologie e contraddizioni.

### Fase 4 — Indici normativa + giurisprudenza

Indici A e B con chunker specifici. Codice penale da Normattiva, 100-200 sentenze pubbliche di test.

### Fase 5 — Router e orchestratore

Router con LLM piccolo, multi-indice, eval set espanso a 100 domande.

### Fase 6 — Verifica citazioni + UI Streamlit

Verificatore fuzzy, UI minima con citazioni cliccabili.

### Fase 7 — Migrazione produzione (futura)

Docker compose su hardware nuovo (probabile NVIDIA). Strato di anonimizzazione per dati Zona Gialla. LLM cloud EU (Mistral Le Plateforme, Bedrock EU, o GPU dedicata Scaleway/OVH/Hetzner).

## Struttura progetto

```
~/forensic-rag/
├── .venv/                    # virtualenv Python host (gitignored)
├── .env                      # config GPU-specific (gitignored)
├── .gitignore
├── docker-compose.yml
├── docker/
│   ├── base-rocm/           # immagine base GPU AMD
│   ├── base-cuda/           # immagine base GPU NVIDIA (futura)
│   ├── whisper/
│   ├── ollama/
│   ├── api/
│   └── ui/
├── src/
│   ├── ingestion/           # parser, chunker per tipo documento
│   ├── retrieval/           # retrieval ibrido + reranker
│   ├── extraction/          # estrazione fatti strutturati
│   ├── router/              # router di query
│   ├── api/                 # FastAPI
│   └── ui/                  # Streamlit
├── data/
│   ├── raw_audio/           # gitignored
│   ├── raw_docs/            # gitignored
│   ├── transcripts/         # gitignored
│   └── processed/           # gitignored
├── indexes/
│   ├── chroma/              # gitignored
│   └── bm25/                # gitignored
├── models/                   # gitignored
├── configs/
├── scripts/
├── notebooks/
└── eval/                     # eval set di domande con risposta attesa
```

## Variabili d'ambiente decise (.env)

```
# GPU backend: 'rocm' for AMD, 'cuda' for NVIDIA
GPU_BACKEND=rocm
GPU_DEVICE=cuda  # PyTorch device name (always 'cuda' even on ROCm)

# ROCm specific (AMD only)
HIP_VISIBLE_DEVICES=0
ROCR_VISIBLE_DEVICES=0
HSA_OVERRIDE_GFX_VERSION=12.0.0  # se serve per gfx1200

# Model config (tune per machine)
LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
LLM_GPU_LAYERS=32
WHISPER_MODEL=large-v3
WHISPER_COMPUTE_TYPE=float16
WHISPER_BATCH_SIZE=4

# Paths (host)
DATA_DIR=./data
INDEX_DIR=./indexes
MODEL_CACHE=./models
```

## Valori decisi da non rimettere in discussione

- Python 3.12
- PyTorch con index ROCm 6.2 (retrocompatibile con ROCm 7.2 a sistema)
- LlamaIndex (non LangChain) come framework RAG
- ChromaDB (non Pinecone/Weaviate cloud) per vector store
- SQLite (non Postgres) per fact extraction nel prototipo
- BGE-M3 come embedder, bge-reranker-v2-m3 come reranker
- Qwen 2.5 7B come LLM principale del prototipo (Llama 3.1 8B come fallback)
- WhisperX come primary, whisper.cpp come fallback se ROCm dà problemi
- Streamlit come UI prototipo (non Gradio, non React)
- FastAPI come backend

## Valutazione

Prima di scrivere il primo chunker, costruire un **eval set**: 50 domande con risposta attesa, etichettate per tipo (fattuale/analogica/normativa/contraddittoria/cronologica), con chunk sorgente atteso. Necessario per sapere se ogni modifica migliora o peggiora il sistema. Costruito con materiale pubblico (sentenze Italgiure + codici Normattiva + caso finto inventato).

## Note operative e "lezioni apprese" finora

- L'installer `amdgpu-install` 7.2.2 aggiunge un repo fantasma `graphics/7.2.2` dentro `rocm.list`. Va rimosso prima di procedere
- Per la 9060 XT usare `--usecase=rocm` **senza** `graphics` — il driver grafico è già nel kernel mainline
- `--no-dkms` obbligatorio con kernel mainline recente
- Ryzen 7700 ha iGPU che ROCm vede come Device 1 — sempre escluderla con `HIP_VISIBLE_DEVICES=0`
- PyTorch ROCm 6.2 wheel è più stabile di 7.x per ora, gira comunque sopra ROCm 7.2 host

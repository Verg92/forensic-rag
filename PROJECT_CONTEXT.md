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

**Tutto in Docker, niente installazioni native.** Host ha solo driver GPU. Stack applicativo tutto in container. Questo abilita migrazione facile tra macchine/GPU.

**Backend GPU: solo CUDA.** Dockerfile con `ARG GPU_BACKEND=rocm|cuda`, ma il branch `rocm` non è testato e l'immagine ROCm è stata eliminata. Si usa esclusivamente il branch `cuda`. La RX 9060 XT (gfx1200) non è supportata da ROCm, quindi abbandonata.

**Compliance.** Dati di natura penale = art. 10 GDPR + D.Lgs. 51/2018. Segreto professionale avvocato. AI Act EU come framework. Nessun transito su server USA non controllati. Scelta strumenti come Plaud rigettata per questo motivo (server USA, LLM di terzi nella pipeline).

## Hardware attuale (prototipo)

- **OS:** Windows con WSL2 (Ubuntu, kernel 6.6.87.2-microsoft-standard-WSL2)
- **GPU:** NVIDIA GTX 1050 — CUDA funzionante via WSL2 NVIDIA passthrough
- **Docker:** Docker Desktop su Windows, accessibile da WSL2

**Perché siamo qui:** Il piano originale era AMD RX 9060 XT (RDNA4, gfx1200) + ROCm su Ubuntu dual boot. Abbandonato perché ROCm non supporta ancora gfx1200 → fallback sempre su CPU → inutilizzabile. Migrazione a macchina Windows + GTX 1050 CUDA che funziona.

## Hardware futuro (produzione)

Opzione ibrida concordata:
- PC locale modesto in studio per task continuativi (WhisperX, embedder, LLM piccolo) — budget ~4.000€
- Cloud GPU EU on-demand per task pesanti su dato anonimizzato (Scaleway L40S o simile) — ~50-200€/mese stimati
- **GPU futura: NVIDIA** (architettura già predisposta per CUDA)

## Stack tecnico deciso

| Livello | Componente | Scelta | Stato |
|---|---|---|---|
| OS | WSL2 su Windows | ✅ in uso |
| Driver GPU | NVIDIA CUDA (via WSL2 passthrough) | ✅ funzionante |
| Container | Docker Desktop + Docker Compose | ✅ funzionante |
| ASR | openai-whisper (PyTorch puro, no CTranslate2) | ✅ funzionante |
| Diarizzazione | pyannote.audio 3.3.2 | ✅ funzionante |
| LLM runtime | Ollama con backend CUDA | da fare |
| LLM principale | Qwen 2.5 7B Instruct Q4_K_M (multilingua, buon italiano) | da fare |
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

- [x] WSL2 su Windows configurato
- [x] Driver NVIDIA CUDA funzionanti via WSL2 passthrough
- [x] Docker Desktop installato e accessibile da WSL2
- [x] Struttura cartelle progetto creata
- [x] Dockerfile whisper con dual-backend (cuda/rocm), branch cuda attivo
- [x] docker-compose.yml configurato per NVIDIA GPU
- [x] .env con GPU_BACKEND=cuda

### ✅ Fase 1 — Pipeline di trascrizione (COMPLETATA per il prototipo)

Obiettivo raggiunto: WhisperX (openai-whisper puro) + pyannote in container Docker, input audio italiano multi-speaker, output JSON strutturato `{speaker, start, end, text}`.

- [x] Dockerfile per container whisper con backend CUDA
- [x] Test con audio pubblico italiano (colloquio psicologico YouTube, 16 min, 2 speaker)
- [x] Output JSON strutturato salvato in `data/transcripts/test.json`
- [x] Qualità trascrizione: buona su audio pulito (valutazione visiva — WER formale da fare)
- [x] Diarizzazione: 2 speaker identificati correttamente, qualche segmento UNKNOWN su transizioni rapide
- [x] Script helper `scripts/transcribe.sh` per invocare il container (gestisce video, path assoluti/relativi, errori chiari)
- [x] Caching modelli: Whisper → `models/whisper_cache`, pyannote → `models/hf_cache` (download una tantum)
- [x] Pulizia Docker: immagine ROCm eliminata, build cache azzerata (~45GB recuperati)
- [ ] Script per mappare SPEAKER_00 → nomi reali (da fare, basso impatto)
- [ ] Test su audio più lungo con 2-4 speaker
- [ ] WER formale su audio con ground truth

**Note sulla qualità attuale:**
- Un errore di speaker swap rilevato su transizione rapida (~108s): pyannote confonde brevemente i due speaker
- Segmenti UNKNOWN = transizioni dove la sovrapposizione è sotto il threshold 0.3 in `align.py`
- `faster-whisper` (CTranslate2) NON è in uso — si usa `openai-whisper` puro con PyTorch+CUDA, più stabile

### 🔜 Fase 2 — Indice caso corrente (PROSSIMA)

Solo indice C prima. Chunker per trascrizioni e atti, metadati ricchi, ChromaDB+BM25, retrieval semplice. Test su caso finto.

**Da fare:**
- [ ] Chunker per trascrizioni (input: JSON da pipeline, output: chunk con metadati speaker/timestamp)
- [ ] Chunker per atti PDF/DOCX (input: documento, output: chunk per sezione/paragrafo)
- [ ] Setup ChromaDB persistente in Docker
- [ ] Setup BM25 (rank_bm25) per keyword search
- [ ] Retrieval ibrido (BM25 + semantic) con scoring combinato
- [ ] BGE-M3 come embedder
- [ ] Test su caso finto: 1 trascrizione + 2-3 atti inventati
- [ ] 10 domande di eval sul caso finto con risposta attesa

### Fase 3 — Estrazione fatti strutturati

SQLite + prompt LLM per estrarre fatti atomici durante ingestione. Query SQL per cronologie e contraddizioni.

### Fase 4 — Indici normativa + giurisprudenza

Indici A e B con chunker specifici. Codice penale da Normattiva, 100-200 sentenze pubbliche di test.

### Fase 5 — Router e orchestratore

Router con LLM piccolo, multi-indice, eval set espanso a 100 domande.

### Fase 6 — Verifica citazioni + UI Streamlit

Verificatore fuzzy, UI minima con citazioni cliccabili.

### Fase 7 — Migrazione produzione (futura)

Docker compose su hardware nuovo (probabile NVIDIA dedicato). Strato di anonimizzazione per dati Zona Gialla. LLM cloud EU (Mistral Le Plateforme, Bedrock EU, o GPU dedicata Scaleway/OVH/Hetzner).

## Struttura progetto

```
~/forensic-rag/
├── .venv/                    # virtualenv Python host (gitignored)
├── .env                      # config GPU-specific (gitignored)
├── .gitignore
├── docker-compose.yml
├── docker/
│   └── whisper/
│       ├── Dockerfile        # dual-backend cuda/rocm, branch cuda attivo
│       └── requirements.txt
├── src/
│   ├── transcription/
│   │   ├── pipeline.py       # entry point: whisper + pyannote + align
│   │   └── align.py          # fusione segmenti whisper + turni pyannote
│   ├── ingestion/            # parser, chunker per tipo documento (da fare)
│   ├── retrieval/            # retrieval ibrido + reranker (da fare)
│   ├── extraction/           # estrazione fatti strutturati (da fare)
│   ├── router/               # router di query (da fare)
│   ├── api/                  # FastAPI (da fare)
│   └── ui/                   # Streamlit (da fare)
├── data/
│   ├── raw_audio/            # gitignored
│   ├── raw_docs/             # gitignored
│   ├── transcripts/          # gitignored (test.json presente)
│   └── processed/            # gitignored
├── indexes/
│   ├── chroma/               # gitignored
│   └── bm25/                 # gitignored
├── models/                   # gitignored
│   ├── hf_cache/             # modelli pyannote (HF_HOME, persistenti)
│   └── whisper_cache/        # modello Whisper large-v3 (~3GB, persistente)
├── configs/
├── docs/
│   └── guida_trascrizione.md # guida uso pipeline
├── scripts/
│   └── transcribe.sh         # wrapper docker compose run whisper
├── notebooks/
└── eval/                     # eval set di domande con risposta attesa
```

## Variabili d'ambiente (.env)

```
# GPU backend: 'cuda' per NVIDIA
GPU_BACKEND=cuda

# HuggingFace token (richiesto da pyannote/speaker-diarization-3.1)
HF_TOKEN=...

# Model config
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

- Python 3.11 nel container (3.12 sull'host se serve)
- PyTorch CUDA via index `cu124`
- openai-whisper (PyTorch puro) — NO faster-whisper/CTranslate2 per ora
- LlamaIndex (non LangChain) come framework RAG
- ChromaDB (non Pinecone/Weaviate cloud) per vector store
- SQLite (non Postgres) per fact extraction nel prototipo
- BGE-M3 come embedder, bge-reranker-v2-m3 come reranker
- Qwen 2.5 7B come LLM principale del prototipo (Llama 3.1 8B come fallback)
- Streamlit come UI prototipo (non Gradio, non React)
- FastAPI come backend

## Valutazione

Prima di scrivere il primo chunker, costruire un **eval set**: domande con risposta attesa, etichettate per tipo (fattuale/analogica/normativa/contraddittoria/cronologica), con chunk sorgente atteso. Necessario per sapere se ogni modifica migliora o peggiora il sistema. Costruito con materiale pubblico (sentenze Italgiure + codici Normattiva + caso finto inventato).

## Note operative e "lezioni apprese" finora

- **AMD RX 9060 XT (gfx1200, RDNA4) non supportata da ROCm** — PyTorch ROCm fa sempre fallback su CPU. Motivo del cambio macchina.
- **WSL2 + NVIDIA:** CUDA funziona tramite passthrough driver Windows. Docker Desktop gestisce le GPU reservation (`driver: nvidia, capabilities: [gpu]`).
- **openai-whisper su CUDA:** `fp16=True` quando device è cuda — obbligatorio per stare nei limiti VRAM della GTX 1050.
- **pyannote/speaker-diarization-3.1** richiede HF_TOKEN e accettazione esplicita dei termini sul sito HuggingFace (una volta sola per account).
- **huggingface-hub:** pyannote 3.3.2 usa ancora `use_auth_token` deprecato — vincolo `huggingface-hub>=0.20.0,<0.23.0` nel requirements.txt per evitare breaking change.
- **numpy<2.0** obbligatorio — pyannote non è ancora compatibile con numpy 2.x.
- **Segmenti UNKNOWN in align.py:** prodotti quando la sovrapposizione Whisper/pyannote è < 0.3 del segmento. Normale su transizioni rapide o voci sovrapposte.
- **Caching modelli:** openai-whisper usa `~/.cache/whisper` di default (non rispetta `HF_HOME`). Passare `download_root` esplicitamente a `whisper.load_model()` e montare un volume dedicato `models/whisper_cache:/app/whisper_cache`.
- **Docker e spazio su disco:** ogni rebuild accumula build cache e immagini orfane. Dopo cambi significativi: `docker builder prune -f` e `docker image prune`. L'immagine `forensic-rag/whisper:cuda` pesa ~9-10GB (PyTorch+CUDA) — è normale.
- **models/ owned da root:** Docker crea le directory dei bind mount come root. Se serve scrivere dall'host: `sudo chown -R $USER:$USER models/`.

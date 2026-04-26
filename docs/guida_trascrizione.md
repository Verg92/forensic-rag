# Guida operativa — Forensic RAG

---

# Parte 1 — Trascrizione audio/video

## Cosa fa

Prende un file audio o video in italiano, lo trascrive con Whisper e identifica chi parla con pyannote (diarizzazione). Produce un file JSON strutturato con speaker, timestamp e testo.

---

## Formati supportati

**Audio (passano direttamente a Whisper):**
`.wav` `.mp3` `.m4a` `.flac` `.ogg` `.opus`

**Video (l'audio viene estratto automaticamente con ffmpeg):**
`.mp4` `.mkv` `.avi` `.mov` `.webm` `.m4v` `.ts` `.mts`

Non serve estrarre l'audio manualmente — basta passare il file video direttamente.

---

## Prerequisiti

- Docker Desktop in esecuzione
- File `.env` con `HF_TOKEN=...` e `GPU_BACKEND=cuda`
- Container whisper buildato: `docker compose build whisper`

---

## Comando

```bash
./scripts/transcribe.sh <file> [num_speakers]
```

| Argomento | Obbligatorio | Descrizione |
|---|---|---|
| `<file>` | sì | Path del file audio o video, relativo alla root del progetto |
| `[num_speakers]` | no | Numero di persone che parlano — se lo sai, specificalo: migliora la diarizzazione |

**Esempi:**

```bash
# Audio, speaker non noti (pyannote li rileva in automatico)
./scripts/transcribe.sh data/raw_audio/colloquio.wav

# Video con 2 speaker noti
./scripts/transcribe.sh data/raw_audio/udienza.mp4 2

# Audio con 3 speaker noti
./scripts/transcribe.sh data/raw_audio/udienza_marzo.mp3 3
```

L'output va automaticamente in `data/transcripts/<nome_file>.json`.

---

## Opzioni avanzate — docker compose direttamente

```bash
docker compose run --rm whisper \
    --audio /data/raw_audio/udienza.wav \
    --output /data/transcripts/udienza.json \
    --model large-v3 \
    --language it \
    --num-speakers 2
```

| Opzione | Default | Descrizione |
|---|---|---|
| `--audio` | obbligatorio | Path file input dentro il container (sempre `/data/...`) |
| `--output` | obbligatorio | Path JSON output dentro il container (sempre `/data/...`) |
| `--model` | `large-v3` | Modello Whisper: `tiny` `base` `small` `medium` `large-v3` |
| `--language` | `it` | Lingua: `it` `en` `fr` ecc. |
| `--num-speakers` | auto | Numero speaker noti |
| `--dry-run` | — | Verifica solo che la GPU sia raggiungibile, non trascrive |

### Modelli Whisper — velocità vs qualità

| Modello | VRAM | Velocità | Qualità |
|---|---|---|---|
| `tiny` | ~1 GB | molto veloce | bassa |
| `base` | ~1 GB | veloce | discreta |
| `small` | ~2 GB | media | buona |
| `medium` | ~5 GB | lenta | ottima |
| `large-v3` | ~3 GB (fp16) | lenta | migliore |

---

## Output JSON — struttura

```json
{
  "metadata": {
    "audio_file": "udienza.wav",
    "whisper_model": "large-v3",
    "diarization_model": "pyannote/speaker-diarization-3.1"
  },
  "utterances": [
    { "speaker": "SPEAKER_00", "start": 0.0,  "end": 23.0, "text": "Buongiorno..." },
    { "speaker": "SPEAKER_01", "start": 23.5, "end": 45.0, "text": "Volevo chiederle..." }
  ]
}
```

- `SPEAKER_00`, `SPEAKER_01` ecc. sono assegnati in ordine di prima comparsa
- `UNKNOWN` compare su transizioni rapide o voci sovrapposte — è normale
- I nomi reali si mappano manualmente dopo (funzionalità da implementare)

---

## Checkpoint automatico

Se il processo viene interrotto dopo la trascrizione ma prima della diarizzazione, viene salvato un file `<nome>_segments_checkpoint.json`. Al run successivo Whisper viene saltato e si riparte dalla diarizzazione. Il checkpoint si elimina automaticamente a fine elaborazione.

---

## Consigli

- Specifica sempre `num_speakers` se sai quante persone parlano
- Audio telefonico: qualità diarizzazione più bassa, speaker swap su transizioni rapide è normale
- File lunghi (>30 min): possono volerci diversi minuti, tieni d'occhio i log
- Prima di processare audio reali: `data/` è già in `.gitignore`, i file non vengono committati

---

---

# Parte 2 — Ingestion documenti

## Cosa fa

Prende un documento (TXT, PDF, DOCX) o una trascrizione JSON, lo spezza in pezzi (chunk), calcola gli embedding con BGE-M3 e li salva in ChromaDB + BM25. Dopo l'ingestion il documento è interrogabile.

---

## Prerequisiti

- Container ingestion buildato: `docker compose build ingestion`
- Directory `indexes/` presente (creata automaticamente)

---

## Comando

```bash
./scripts/ingest.sh <file> <caso_id> [tipo_atto]
```

| Argomento | Obbligatorio | Descrizione |
|---|---|---|
| `<file>` | sì | Path del file da indicizzare, relativo alla root del progetto |
| `<caso_id>` | sì | Identificatore del caso, es. `caso_001`. Usato per filtrare le ricerche. Usa sempre lo stesso ID per tutti i documenti dello stesso caso |
| `[tipo_atto]` | no (default: `documento`) | Etichetta del tipo di documento: `perizia` `verbale` `relazione` `atto` ecc. Ignorato per le trascrizioni JSON |

**Esempi:**

```bash
# Indicizza una perizia
./scripts/ingest.sh data/raw_docs/perizia.txt caso_001 perizia

# Indicizza un verbale
./scripts/ingest.sh data/raw_docs/verbale_udienza.txt caso_001 verbale

# Indicizza una trascrizione (tipo_atto viene ignorato, rilevato dal .json)
./scripts/ingest.sh data/transcripts/udienza.json caso_001

# Secondo caso — stesso sistema, caso_id diverso
./scripts/ingest.sh data/raw_docs/perizia_rossi.txt caso_002 perizia
```

---

## Dove mettere i file

| Tipo | Cartella |
|---|---|
| Audio/video da trascrivere | `data/raw_audio/` |
| Documenti (PDF, TXT, DOCX) | `data/raw_docs/` |
| Trascrizioni prodotte | `data/transcripts/` (generate automaticamente) |

Tutte queste cartelle sono in `.gitignore` — i tuoi documenti non vengono mai committati su git.

---

## Dry-run — vedi come vengono spezzati i chunk senza indicizzare

Utile per verificare che il chunker stia tagliando bene il documento prima di indicizzarlo davvero:

```bash
docker compose run --rm ingestion \
    --input /data/raw_docs/perizia.txt \
    --caso-id caso_001 \
    --tipo-atto perizia \
    --dry-run
```

Stampa tutti i chunk con ID e metadati, senza scrivere nulla negli indici.

---

---

# Parte 3 — Ricerca (retrieval)

## Cosa fa

Data una domanda in italiano, cerca nei documenti indicizzati i pezzi più rilevanti. Usa due sistemi in parallelo — ricerca per significato (semantica) e ricerca per parole chiave (BM25) — e combina i risultati. Restituisce i chunk più pertinenti con la fonte esatta (da quale documento, a quale timestamp se è una trascrizione).

---

## Comando

```bash
./scripts/query.sh "<domanda>" [top_k] [caso_id]
```

| Argomento | Obbligatorio | Descrizione |
|---|---|---|
| `"<domanda>"` | sì | La domanda o il testo da cercare, tra virgolette |
| `[top_k]` | no (default: 5) | Quanti risultati restituire |
| `[caso_id]` | no | Se specificato, filtra solo i documenti di quel caso |

**Esempi:**

```bash
# Cerca su tutti i documenti indicizzati
./scripts/query.sh "Il padre ha fatto il parent training?"

# Cerca solo nel caso 001, 5 risultati
./scripts/query.sh "Il padre ha fatto il parent training?" 5 caso_001

# Cerca solo nel caso 001, 3 risultati
./scripts/query.sh "quando è stata formulata la diagnosi di autismo" 3 caso_001

# Cerca una persona specifica
./scripts/query.sh "Dott.ssa Conti" 5 caso_001

# Cerca un evento
./scripts/query.sh "terapia ABA" 5 caso_001
```

---

## Output — cosa ricevi

```
======================================================================
  Query: Il padre ha fatto il parent training?
======================================================================

[1] score=0.0142  [perizia · perizia_psicologica]
    Il padre manifesta difficoltà nell'adattare le proprie aspettative
    alle caratteristiche del figlio. Tende a interpretare il comportamento
    del bambino come rifiuto volontario...

[2] score=0.0098  [verbale · verbale_udienza]
    Dott.ssa Conti: "Non vi è contraddizione. L'assenza di disagio
    manifesto è un dato positivo..."

[3] score=0.0076  [trascrizione · SPEAKER_01 · 09:22]
    Però, come dirle, non mi ha dato abbastanza soddisfazione
    sinceramente, questa terapia...
```

| Campo | Descrizione |
|---|---|
| `score` | Punteggio di rilevanza combinato (vedi sotto) |
| `[tipo · fonte]` | Da quale documento viene il pezzo |
| `[trascrizione · SPEAKER · mm:ss]` | Per le trascrizioni: chi parlava e a che minuto |
| Testo | I primi 200 caratteri del chunk — abbastanza per capire se è rilevante |

### Come leggere lo score

Lo score non è una percentuale. Funziona così: il sistema fa due ricerche in parallelo (semantica e keyword), classifica i risultati di ognuna in una classifica separata, poi li combina con una formula che premia chi è in cima a entrambe.

Il valore massimo teorico è circa **0.0164** (primo posto in entrambe le ricerche). Nella pratica:

| Score | Significato |
|---|---|
| `0.014 – 0.016` | Risultato eccellente — in cima ad entrambe le ricerche |
| `0.008 – 0.013` | Risultato buono — in cima a una delle due ricerche |
| `0.003 – 0.007` | Risultato discreto — presente ma non in prima posizione |
| `< 0.003` | Risultato marginale — trovato per parole comuni ma poco rilevante |

**Esempio concreto:** un risultato con `score=0.0161` su una query "il padre e il parent training" significa che quel chunk era quasi al primo posto sia nella ricerca per significato che in quella per parole chiave — è quasi certamente il pezzo che stai cercando.

L'importante non è il numero in assoluto, ma il **distacco tra il primo e il secondo risultato**: se il primo ha 0.016 e il secondo 0.004, il primo è chiaramente dominante. Se sono tutti intorno a 0.005, il sistema ha trovato molti pezzi vagamente rilevanti ma nessuno chiaramente migliore.

---

## Consigli

- Le domande in italiano naturale funzionano meglio delle parole chiave secche
- Se non trovi quello che cerchi, prova a riformulare con parole diverse
- Usa `caso_id` per non mischiare documenti di casi diversi
- Il `score` non è una percentuale — confronta i risultati tra loro, non con un valore assoluto

---

---

# Parte 4 — Domanda con risposta (RAG completo)

## query.sh vs ask.sh — la differenza

| | `query.sh` | `ask.sh` |
|---|---|---|
| **Cosa fa** | Cerca i chunk rilevanti e li mostra | Cerca i chunk + chiede al LLM di rispondere |
| **Output** | Testo grezzo dei documenti con score | Risposta in italiano con citazioni `[FONTE N]` |
| **Velocità** | Rapido (~5s) | Più lento (~30-60s per generare la risposta) |
| **Quando usarlo** | Per esplorare cosa c'è nell'indice, fare debug, verificare il retrieval | Per ottenere una risposta sintetizzata a una domanda specifica |

**Regola pratica:** se `query.sh` non trova i chunk giusti, `ask.sh` non può rispondere bene. Inizia sempre con `query.sh` per verificare che il retrieval funzioni, poi usa `ask.sh` per la risposta finale.

---

## Cosa fa

Prende una domanda in italiano, recupera i chunk più rilevanti (come `query.sh`), li passa a Qwen 2.5 3B via Ollama, e riceve una risposta in italiano con citazioni alle fonti.

---

## Prerequisiti

- Docker Desktop in esecuzione
- Ollama avviato (lo script lo avvia in automatico se non è già attivo)
- Modello Qwen scaricato (la prima volta ci vogliono ~2GB, poi è in cache in `models/ollama/`)

---

## Comando

```bash
./scripts/ask.sh "<domanda>" [caso_id] [top_k]
```

| Argomento | Obbligatorio | Descrizione |
|---|---|---|
| `"<domanda>"` | sì | La domanda in italiano, tra virgolette |
| `[caso_id]` | no | Se specificato, filtra solo i documenti di quel caso |
| `[top_k]` | no (default: 5) | Quanti chunk passare al LLM come contesto |

**Esempi:**

```bash
# Domanda su un caso specifico
./scripts/ask.sh "Il padre ha fatto il parent training?" caso_001

# Più contesto al LLM (utile se la risposta sembra incompleta)
./scripts/ask.sh "Il padre ha fatto il parent training?" caso_001 8

# Domanda aperta su tutti i documenti
./scripts/ask.sh "Quali terapie sta seguendo il bambino?"
```

---

## Output — cosa ricevi

```
======================================================================
  Domanda: Il padre ha fatto il parent training?
======================================================================

Il padre non aveva ancora avviato il percorso di parent training al momento
dell'udienza. Il Tribunale lo ha ordinato con obbligo di avvio entro trenta
giorni, con deposito di conferma scritta in cancelleria [FONTE 1].
La perizia raccomandava invece il parent training per la madre, con
l'obiettivo di ridurre i comportamenti iperprotettivi [FONTE 5].

──────────────────────────────────────────────────────────────────────
  Fonti usate:
  [1] Verbale: verbale_udienza  (score 0.0159)
  [2] Verbale: verbale_udienza  (score 0.0158)
  ...
  [5] Perizia: perizia_psicologica  (score 0.0155)
```

Le citazioni `[FONTE N]` corrispondono alla lista numerata sotto. Puoi verificare il testo originale eseguendo `query.sh` con le stesse parole chiave.

---

## Consigli

- Se la risposta dice "l'informazione non è presente", prima di preoccuparti esegui `query.sh` con le stesse parole chiave: se i chunk giusti ci sono, il problema è la formulazione della domanda o il `top_k` troppo basso
- Aumenta `top_k` a 8-10 se la risposta sembra tagliata o dice che non ha abbastanza informazioni
- Il LLM (Qwen 3B) è un modello piccolo: per domande complesse o molto specifiche può essere impreciso — verifica sempre sulle fonti citate
- La prima risposta dopo l'avvio di Ollama può essere lenta (~60s); le successive sono più rapide

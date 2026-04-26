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
./scripts/transcribe.sh <file> <caso_id> [num_speakers]
```

| Argomento | Obbligatorio | Descrizione |
|---|---|---|
| `<file>` | sì | Path del file audio o video, dentro `data/raw_audio/` |
| `<caso_id>` | sì | Identificatore del caso — il JSON finisce direttamente in `data/raw_docs/<caso_id>/` |
| `[num_speakers]` | no | Numero di persone che parlano — se lo sai, specificalo: migliora la diarizzazione |

**Esempi:**

```bash
# Audio, speaker non noti (pyannote li rileva in automatico)
./scripts/transcribe.sh data/raw_audio/colloquio.wav caso_001

# Video con 2 speaker noti
./scripts/transcribe.sh data/raw_audio/udienza.mp4 caso_001 2

# Audio con 3 speaker noti
./scripts/transcribe.sh data/raw_audio/udienza_marzo.mp3 caso_001 3
```

L'output va automaticamente in `data/raw_docs/<caso_id>/<nome_file>.json` — già nella cartella giusta per l'ingest, senza spostamenti manuali.

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

## Come funziona il sistema — due momenti distinti

Il sistema lavora in due fasi separate, e capire questa distinzione spiega perché i comandi hanno argomenti diversi.

**Momento 1 — Ingest** (`ingest.sh`): legge i file dal disco e li carica nel database. Ha bisogno di sapere dove stanno i file → vuole un **path di cartella**.

**Momento 2 — Tutto il resto** (`extract.sh`, `query.sh`, `ask.sh`, `facts.sh`): lavora esclusivamente sul database, non tocca più i file originali. Non sa niente di cartelle o path → vuole solo il **nome del caso** (`caso_id`) per filtrare i dati nel database.

```
FILESYSTEM                          DATABASE (indexes/)
──────────────────────              ─────────────────────────────────────
data/raw_docs/caso_001/             ChromaDB: chunk con caso_id="caso_001"
  perizia.txt            →ingest→   BM25:     chunk con caso_id="caso_001"
  verbale.txt                       SQLite:   fatti con caso_id="caso_001"
  udienza.json
       ↑
  dopo l'ingest
  questi file non
  servono più al sistema
```

### Dove vivono i dati — tre database locali

Tutti dentro `indexes/`, tutto locale, niente esce dalla macchina.

| Database | Path | Cosa contiene | Dimensione tipica |
|---|---|---|---|
| ChromaDB | `indexes/chroma/` | vettori embedding + testo chunk + metadati | ~50-100 MB per caso |
| BM25 | `indexes/bm25/index.pkl` | indice keyword + testo + metadati | ~5-10 MB |
| SQLite | `indexes/facts.db` | fatti strutturati (solo dopo `extract.sh`) | ~1-2 MB |

Per verificare lo spazio occupato:
```bash
du -sh indexes/
```

---

### Perché tre database diversi — a cosa serve ciascuno

**ChromaDB — ricerca per significato**

Quando indicizzi un documento, il testo viene prima spezzato in pezzi (chunk) e poi ogni pezzo viene trasformato in un vettore numerico da BGE-M3 — un elenco di ~1000 numeri che rappresenta il "significato" di quel testo nello spazio semantico. ChromaDB salva sia il testo originale del chunk che il suo vettore.

Quando cerchi "il bambino ha problemi relazionali", il sistema trasforma anche la domanda in un vettore e cerca i chunk il cui vettore è matematicamente vicino. Questo permette di trovare testi che parlano della stessa cosa con parole diverse: "difficoltà nell'interazione sociale" o "deficit nelle relazioni interpersonali" vengono trovati anche se non contengono le parole esatte della domanda.

Il limite: non distingue bene nomi propri, date, numeri, termini tecnici specifici.

**BM25 — ricerca per parole chiave**

È il motore di ricerca classico (lo stesso usato dai motori di ricerca prima del machine learning). Cerca i chunk che contengono esattamente le parole della domanda, pesando la frequenza e la rarità di ogni parola nel corpus.

Quando cerchi "Dott.ssa Conti" o "parent training" o "articolo 337-ter", BM25 li trova con precisione — mentre la ricerca semantica potrebbe confondersi perché nomi propri e termini tecnici hanno un significato "piatto" nello spazio vettoriale.

Il limite: non capisce sinonimi o riformulazioni.

**Perché usarli insieme**

I due sistemi si compensano. `query.sh` e `ask.sh` li eseguono in parallelo e combinano i risultati con una formula (Reciprocal Rank Fusion): i chunk che risultano rilevanti in entrambe le ricerche scalano in cima. Questo è il "retrieval ibrido" — più robusto di ciascuno dei due da solo.

**SQLite — fatti strutturati**

ChromaDB e BM25 restituiscono pezzi di testo — sei tu (o il LLM) a dover leggere e interpretare. SQLite contiene invece fatti già estratti e classificati: `[scadenza] padre: avviare parent training`, `[diagnosi] bambino: DSA`.

Serve per domande strutturate che il RAG gestisce male:
- "Quali scadenze ci sono in questo caso?" → `facts.sh caso_001 scadenza`
- "Cosa è stato diagnosticato al bambino?" → `facts.sh caso_001 diagnosi bambino`
- "Quali raccomandazioni ha fatto la perizia?" → `facts.sh caso_001 raccomandazione`

Con il RAG dovresti sapere già cosa cercare per trovarlo. Con SQLite puoi esplorare per categoria.

Quindi i comandi si usano così:

```bash
# Ingest: vuole il path (legge dal disco)
./scripts/ingest.sh data/raw_docs/caso_001/

# Tutti gli altri: vogliono il nome del caso (leggono dal database)
./scripts/extract.sh caso_001
./scripts/query.sh "domanda" 5 caso_001
./scripts/ask.sh "domanda" caso_001
./scripts/facts.sh caso_001
```

Il `caso_id` è semplicemente il nome che hai dato alla cartella — diventa il tag con cui tutti i dati di quel caso vengono etichettati nel database.

---

## Cosa fa

Prende un documento (TXT, PDF, DOCX) o una trascrizione JSON, lo spezza in pezzi (chunk), calcola gli embedding con BGE-M3 e li salva in ChromaDB + BM25. Dopo l'ingest il documento è interrogabile tramite `query.sh` e `ask.sh`.

I dati indicizzati vengono scritti in `indexes/` e ci restano finché non li cancelli esplicitamente. Non si perdono tra un avvio e l'altro del container.

---

## Prerequisiti

- Container ingestion buildato: `docker compose build ingestion`

---

## Struttura cartelle — come organizzare i casi

Ogni caso ha una cartella dedicata dentro `data/raw_docs/`. Il nome della cartella diventa automaticamente il `caso_id`.

```
data/
  raw_audio/                        ← audio/video da trascrivere
  raw_docs/
    caso_001/                       ← tutti i file del caso 001 (docs + trascrizioni)
      perizia_psicologica.txt       ← copiato a mano
      verbale_udienza.txt           ← copiato a mano
      relazione_ctu.docx            ← copiato a mano
      udienza_marzo.json            ← generato da transcribe.sh direttamente qui
    caso_002/                       ← caso diverso, indice separato
      perizia.txt
      verbale.txt
```

Tutte queste cartelle sono in `.gitignore` — i tuoi documenti non vengono mai committati su git.

### Come si chiama il caso_id?

È il **nome della cartella** — niente di più. Quando cerchi con `query.sh "domanda" 5 caso_001`, il sistema restituisce solo i chunk che provengono da quella cartella. Se hai un solo caso puoi anche non specificarlo e il sistema cerca su tutto.

Non esiste un registro centrale dei casi: il `caso_id` vive come metadato su ogni chunk dentro `indexes/`. Se vuoi sapere quali casi hai indicizzato, devi ricordartelo tu (o usare il comando di verifica qui sotto).

### Come si chiama il tipo_atto?

Viene ricavato **automaticamente dal nome del file** — non devi specificarlo. La regola è semplice: se il nome del file inizia con una parola riconosciuta, quella diventa il tipo:

| Nome file | Tipo rilevato |
|---|---|
| `perizia_psicologica.txt` | `perizia` |
| `verbale_udienza.txt` | `verbale` |
| `relazione_ctu.docx` | `relazione` |
| `atto_nomina.pdf` | `atto` |
| `sentenza_tribunale.txt` | `sentenza` |
| `qualsiasi_altro_nome.txt` | `documento` |
| `udienza.json` | `trascrizione` (sempre, per i .json) |

Parole riconosciute: `perizia`, `verbale`, `relazione`, `atto`, `consulenza`, `sentenza`, `ordinanza`.

Il tipo appare nelle citazioni delle risposte: `Perizia: perizia_psicologica`, `Verbale: verbale_udienza`. È solo un'etichetta leggibile — il sistema non ci fa nessuna logica sopra.

### Le trascrizioni

`transcribe.sh` salva automaticamente i JSON in `data/transcripts/`. Per includerle nell'indice di un caso, **copiale nella cartella del caso** prima di fare ingest:

```bash
cp data/transcripts/udienza_marzo.json data/raw_docs/caso_001/
```

---

## Comando

```bash
# Indicizza tutta la cartella di un caso (modo consigliato)
./scripts/ingest.sh data/raw_docs/caso_001/

# Indicizza un file singolo (caso_id e tipo_atto espliciti)
./scripts/ingest.sh data/raw_docs/perizia.txt caso_001 perizia
```

### Modalità cartella

```bash
./scripts/ingest.sh data/raw_docs/caso_001/
```

- `caso_id` = nome della cartella (`caso_001`)
- `tipo_atto` = rilevato dal nome file (vedi tabella sopra)
- Processa tutti i file nella cartella in sequenza
- Aggiunge i chunk all'indice senza cancellare quelli già presenti

### Modalità file singolo

```bash
./scripts/ingest.sh <file> <caso_id> [tipo_atto]
```

- `caso_id` obbligatorio (non può essere ricavato dal path)
- `tipo_atto` opzionale: se omesso viene rilevato dal nome file, altrimenti `documento`
- Utile per aggiungere un documento a un caso già indicizzato

---

## Workflow tipico per un nuovo caso

```bash
# 1. Crea la cartella del caso e copia i documenti scritti
mkdir -p data/raw_docs/caso_001
cp /percorso/perizia_psicologica.txt data/raw_docs/caso_001/
cp /percorso/verbale_udienza.txt     data/raw_docs/caso_001/

# 2. Trascrivi gli audio — il JSON va direttamente nella cartella del caso
./scripts/transcribe.sh data/raw_audio/udienza.mp4 caso_001 2

# 3. Indicizza tutto in un colpo
./scripts/ingest.sh data/raw_docs/caso_001/

# 4. Verifica
./scripts/query.sh "test" 3 caso_001
```

---

## Dry-run — vedi come vengono spezzati i chunk senza indicizzare

Utile per verificare che il chunker stia tagliando bene il documento prima di indicizzarlo davvero:

```bash
docker compose run --rm ingestion \
    --input /data/raw_docs/caso_001/perizia_psicologica.txt \
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
- Il LLM (Qwen 7B) può essere impreciso su domande molto specifiche — verifica sempre sulle fonti citate
- La prima risposta dopo l'avvio di Ollama può essere lenta (~60s); le successive sono più rapide

---

---

# Parte 5 — Fatti strutturati (estrazione e consultazione)

## Perché esiste, in aggiunta al RAG

`ask.sh` risponde bene a domande aperte ("cosa dice la perizia sul padre?"), ma è impreciso su domande strutturate come "quali scadenze ci sono?" o "quando è stata fatta la diagnosi?" — perché deve indovinare quali chunk cercare e sintetizzare testo libero.

La Parte 5 affianca il RAG con un database strutturato: dopo l'ingest, un LLM analizza ogni chunk e ne estrae fatti atomici (scadenze, diagnosi, terapie, raccomandazioni...) salvandoli in SQLite. Da quel momento puoi interrogare i fatti direttamente, con filtri precisi.

---

## Workflow

```bash
# 1. Indicizza i documenti (Parte 2)
./scripts/ingest.sh data/raw_docs/caso_001/

# 2. Estrai i fatti strutturati (una volta sola, o dopo nuovi documenti)
./scripts/extract.sh caso_001

# 3. Consulta i fatti
./scripts/facts.sh caso_001
./scripts/facts.sh caso_001 scadenza
./scripts/facts.sh caso_001 diagnosi bambino
```

I comandi 2 e 3 usano il nome del caso (`caso_001`), non un path — perché lavorano sul database, non sui file originali (vedi la spiegazione dei due momenti in Parte 2).

---

## extract.sh — estrazione fatti

```bash
./scripts/extract.sh <caso_id> [--dry-run]
```

Legge tutti i chunk di quel caso da ChromaDB, li passa uno per uno a Ollama, e salva i fatti estratti in `indexes/facts.db` (SQLite).

**Tipi di fatto estratti:** `affermazione`, `negazione`, `ammissione`, `opinione`, `scadenza`, `raccomandazione`, `diagnosi`, `terapia`

**Attenzione ai tempi:** ogni chunk richiede una chiamata a Ollama. Con 87 chunk e il modello 7B su GTX 1050 Ti, aspettati 15-20 minuti. L'estrazione si fa una volta sola per caso (o dopo aver aggiunto nuovi documenti).

### --dry-run

```bash
./scripts/extract.sh caso_001 --dry-run
```

Chiama comunque Ollama e mostra i fatti estratti a schermo, **senza scrivere nulla su SQLite**. Serve per verificare che il LLM stia estraendo cose sensate prima di popolare il database. Se l'output è sbagliato puoi correggere il prompt e riprovare senza aver sporcato il DB.

Esempio di output dry-run:
```
[caso_001_verbale_udienza_001] verbale_udienza → 2 fatti
  [scadenza] padre: avviare parent training entro 30 giorni dall'udienza
  [raccomandazione] madre: parent training per ridurre comportamenti iperprotettivi

[caso_001_perizia_psicologica_003] perizia_psicologica → 1 fatto
  [diagnosi] bambino: DSA diagnosticato
```

---

## facts.sh — consultazione fatti

```bash
./scripts/facts.sh <caso_id> [tipo] [soggetto]
```

| Argomento | Obbligatorio | Descrizione |
|---|---|---|
| `<caso_id>` | sì | Nome del caso nel database |
| `[tipo]` | no | Filtra per tipo: `scadenza` `diagnosi` `terapia` `raccomandazione` ecc. |
| `[soggetto]` | no | Filtra per soggetto (es: `padre` `madre` `bambino`) |

**Esempi:**

```bash
# Tutti i fatti del caso
./scripts/facts.sh caso_001

# Solo le scadenze
./scripts/facts.sh caso_001 scadenza

# Diagnosi relative al bambino
./scripts/facts.sh caso_001 diagnosi bambino

# Tutto quello che riguarda il padre
./scripts/facts.sh caso_001 "" padre
```

Esempio di output:
```
============================================================
  Caso: caso_001  |  tipo: scadenza
  Totale: 2 fatti
============================================================

────────────────────────────────────────────────────────────
  SCADENZA (2)
────────────────────────────────────────────────────────────
  • padre: avviare parent training  [entro 30 giorni dall'udienza]
    ↳ verbale: verbale_udienza
  • padre: depositare conferma scritta in cancelleria  [entro 30 giorni]
    ↳ verbale: verbale_udienza
```

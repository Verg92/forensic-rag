# Guida alla trascrizione audio/video

## Cosa fa la pipeline

Prende un file audio o video in italiano, lo trascrive con Whisper e identifica chi parla con pyannote (diarizzazione). Produce un file JSON strutturato con speaker, timestamp e testo.

---

## Formati supportati

**Audio (passano direttamente a Whisper):**
`.wav` `.mp3` `.m4a` `.flac` `.ogg` `.opus`

**Video (l'audio viene estratto automaticamente con ffmpeg prima della trascrizione):**
`.mp4` `.mkv` `.avi` `.mov` `.webm` `.m4v` `.ts` `.mts`

Non serve estrarre l'audio manualmente — basta passare il file video direttamente.

---

## Prerequisiti

- Docker Desktop in esecuzione
- File `.env` con `HF_TOKEN=...` e `GPU_BACKEND=cuda`
- Container `forensic-rag/whisper:cuda` già buildato (se non lo è: `docker compose build whisper`)

---

## Comando rapido — script wrapper

```bash
./scripts/transcribe.sh <file> [num_speaker]
```

**Esempi:**

```bash
# Audio, speaker non noti
./scripts/transcribe.sh data/raw_audio/udienza.wav

# Video, 2 speaker noti
./scripts/transcribe.sh data/raw_audio/colloquio.mp4 2

# Audio, 3 speaker noti
./scripts/transcribe.sh data/raw_audio/udienza_marzo.mp3 3
```

L'output finisce automaticamente in `data/transcripts/<nome_file>.json`.

---

## Comando completo — docker compose direttamente

Utile se vuoi cambiare modello, lingua o output path:

```bash
docker compose run --rm whisper \
    --audio /data/raw_audio/udienza.wav \
    --output /data/transcripts/udienza.json \
    --model large-v3 \
    --language it \
    --num-speakers 2
```

### Opzioni disponibili

| Opzione | Default | Descrizione |
|---|---|---|
| `--audio` | obbligatorio | Path del file input (audio o video) |
| `--output` | obbligatorio | Path del JSON output |
| `--model` | `large-v3` | Modello Whisper (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `--language` | `it` | Lingua audio (ISO 639-1: `it`, `en`, `fr`…) |
| `--num-speakers` | auto | Numero speaker noti — migliora la diarizzazione se specificato |
| `--dry-run` | — | Testa solo che la GPU sia raggiungibile, non trascrive |

### Modelli Whisper: velocità vs qualità

| Modello | VRAM richiesta | Velocità | Qualità |
|---|---|---|---|
| `tiny` | ~1 GB | molto veloce | bassa |
| `base` | ~1 GB | veloce | discreta |
| `small` | ~2 GB | buona | buona |
| `medium` | ~5 GB | lenta | ottima |
| `large-v3` | ~10 GB fp32 / ~3 GB fp16 | lenta | migliore |

Con la GTX 1050 si usa fp16 automaticamente — `large-v3` entra nella VRAM disponibile.

---

## Test GPU (dry-run)

Prima di processare un file lungo, verifica che la GPU sia raggiungibile:

```bash
docker compose run --rm whisper --audio dummy --output dummy --dry-run
```

Deve stampare: `CUDA disponibile: NVIDIA GeForce GTX 1050` (o simile) e uscire.

---

## Output JSON

```json
{
  "metadata": {
    "audio_file": "udienza.wav",
    "original_format": ".wav",
    "whisper_model": "large-v3",
    "diarization_model": "pyannote/speaker-diarization-3.1",
    "schema_version": "1.0"
  },
  "utterances": [
    {
      "speaker": "SPEAKER_00",
      "start": 0.0,
      "end": 23.0,
      "text": "Buongiorno, come posso aiutarla?"
    },
    {
      "speaker": "SPEAKER_01",
      "start": 23.5,
      "end": 45.0,
      "text": "Volevo chiederle informazioni sul percorso..."
    }
  ]
}
```

I nomi `SPEAKER_00`, `SPEAKER_01` ecc. sono assegnati da pyannote in ordine di prima comparsa. Per mapparli a nomi reali si usa il passo successivo (da implementare).

Il campo `UNKNOWN` compare quando pyannote non riesce ad assegnare un turno con sufficiente certezza (tipico su transizioni rapide o voci sovrapposte).

---

## Checkpoint automatico

Se il processo viene interrotto dopo la trascrizione Whisper ma prima della diarizzazione, viene salvato un file `<nome>_segments_checkpoint.json` accanto all'output. Al run successivo, Whisper viene saltato e si riparte dalla diarizzazione. Il checkpoint viene rimosso automaticamente a fine elaborazione.

---

## Consigli pratici

- **Specifica `--num-speakers`** quando sai quante persone parlano: migliora significativamente la qualità della diarizzazione.
- **Audio telefonico o registrazioni ambientali:** qualità di diarizzazione più bassa — speaker swap su transizioni rapide è normale.
- **File lunghi (>30 min):** la trascrizione può impiegare diversi minuti. Tieni d'occhio i log del container.
- **Prima di processare audio reali di casi:** assicurati che `data/` sia esclusa da git (è già in `.gitignore`).

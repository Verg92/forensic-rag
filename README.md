# Forensic RAG — Guida al deploy su nuova macchina

Sistema RAG locale per studio legale (psicologia forense + avvocatura). Privacy-first: tutto gira in locale tramite Docker, nessun dato sensibile esce dalla macchina.

---

## Requisiti hardware

- Windows 10/11 (64-bit, build 19041 o successiva)
- GPU NVIDIA con almeno 4 GB VRAM (consigliati 6–8 GB per modelli standard)
- Driver NVIDIA aggiornati (≥ 525.x)
- 100 GB di spazio libero (immagini Docker + modelli)

---

## 1. Installazione WSL2

Apri **PowerShell come amministratore** ed esegui:

```powershell
wsl --install Ubuntu-24.04
```
Questo installa WSL2 con Ubuntu come distribuzione predefinita. Riavvia il PC quando richiesto.

Al primo avvio di Ubuntu ti verrà chiesto di creare un utente e una password.

Verifica che WSL2 sia attivo:

```powershell
wsl --list --verbose
```

La colonna `VERSION` deve mostrare `2`. Se mostra `1`:

```powershell
wsl --set-default-version 2
wsl --set-version Ubuntu 2
```
Poi per aggiornare la distro:

```bash
sudo apt update && sudo apt upgrade
```
---

## 2. Driver NVIDIA e CUDA via WSL2

**Non installare CUDA dentro WSL.** I driver NVIDIA si installano solo su Windows; WSL2 li espone automaticamente ai container tramite passthrough.

### 2a. Installa i driver NVIDIA su Windows

Scarica e installa l'ultimo driver per la tua GPU da:
[https://www.nvidia.com/drivers](https://www.nvidia.com/drivers)

Scegli il driver **Game Ready** o **Studio** — entrambi includono il supporto CUDA per WSL2.

### 2b. Verifica dentro WSL

Apri il terminale Ubuntu e controlla:

```bash
nvidia-smi
```

Deve mostrare la tua GPU e la versione CUDA. Se il comando non è trovato, i driver Windows non sono aggiornati.

---

## 3. Docker Desktop

### 3a. Scarica e installa

Scarica Docker Desktop per Windows da:
[https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)

Durante l'installazione assicurati che sia selezionata l'opzione **"Use WSL 2 instead of Hyper-V"**.

### 3b. Configura l'integrazione con WSL

Apri Docker Desktop → **Settings → Resources → WSL Integration** e attiva l'integrazione per la distribuzione Ubuntu.

### 3c. Abilita il supporto GPU

Docker Desktop su Windows gestisce automaticamente le GPU NVIDIA tramite WSL2. Non serve configurazione aggiuntiva: il `docker-compose.yml` del progetto usa già `driver: nvidia`.

### 3d. Verifica

Dal terminale Ubuntu:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

Deve mostrare la stessa GPU vista prima. Se fallisce, riavvia Docker Desktop.

---

## 4. Setup del progetto

### 4a. Clona il repository

```bash
cd ~
git clone <url-del-repository> forensic-rag
cd forensic-rag
```

### 4b. Crea il file `.env`

Il file `.env` **non è nel repository** (contiene credenziali). Crealo manualmente:

```bash
cp .env.example .env   # se esiste, altrimenti crea da zero:
nano .env
```

Contenuto minimo obbligatorio:

```env
# Backend GPU — non cambiare su macchine NVIDIA
GPU_BACKEND=cuda

# Token HuggingFace — richiesto da pyannote per la diarizzazione
# Ottienilo su https://huggingface.co/settings/tokens
HF_TOKEN=hf_...

# Modello LLM — scegli in base alla VRAM disponibile (vedi sezione sotto)
LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
```

### 4c. Scelta del modello LLM in base alla VRAM

| VRAM GPU | Modello consigliato | Note |
|---|---|---|
| 4 GB | `qwen2.5:3b-instruct-q4_K_M` | Minimo funzionante, risposte più brevi |
| 6–8 GB | `qwen2.5:7b-instruct-q4_K_M` | **Configurazione standard del progetto** |
| 10–12 GB | `qwen2.5:14b-instruct-q4_K_M` | Qualità superiore, tempi simili |
| 16+ GB | `qwen2.5:32b-instruct-q4_K_M` | Massima qualità, genera più lentamente |

Imposta il valore scelto in `LLM_MODEL` nel `.env`. Il modello viene scaricato automaticamente al primo `ask.sh`.

Per il modello Whisper (trascrizione), la scelta è in `transcribe.sh` con il flag `--model`:

| VRAM GPU | Modello Whisper | Note |
|---|---|---|
| 4 GB | `medium` | Qualità buona, italiano accettabile |
| 6+ GB | `large-v2` | Qualità alta |
| 6+ GB | `large-v3` | **Default del progetto**, qualità migliore |

### 4d. Token HuggingFace

Il token serve per scaricare il modello `pyannote/speaker-diarization-3.1`. Oltre al token devi **accettare i termini d'uso** del modello sul sito HuggingFace una volta sola:

1. Vai su [https://huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
2. Clicca **"Agree and access repository"**
3. Fai lo stesso per [https://huggingface.co/pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)

Senza questo passaggio il container whisper fallisce con errore 401 anche con un token valido.

### 4e. Cosa trasferire dalla macchina precedente

I dati dei casi e gli indici sono nel `.gitignore`. Se stai migrando da un'altra macchina:

| Cosa | Dove | Note |
|---|---|---|
| Dati casi | `data/raw_audio/`, `data/raw_docs/`, `data/transcripts/` | Copia manuale (dati sensibili) |
| Indici vettoriali | `indexes/chroma/`, `indexes/bm25/` | Opzionale: si rigenera con `ingest.sh` |
| Modelli scaricati | `models/` | Opzionale: si riscaricano automaticamente (~5–10 GB) |
| Configurazione | `.env` | **Obbligatorio**: contiene `HF_TOKEN` |

Se non copi `indexes/`, dopo aver copiato i documenti basta rieseguire `ingest.sh` per ricostruire tutto.

---

## 5. Build delle immagini Docker

Le immagini si costruiscono una volta sola. La prima build scarica PyTorch + dipendenze (~5–10 GB) e richiede 10–20 minuti.

### 5a. Container Whisper (trascrizione audio)

```bash
cd ~/forensic-rag
docker compose build whisper
```

Immagine risultante: `forensic-rag/whisper:cuda` (~9 GB con PyTorch CUDA)

### 5b. Container Ingestion (embedding, retrieval, LLM)

```bash
docker compose build ingestion
```

Immagine risultante: `forensic-rag/ingestion:cpu` (~600 MB, CPU-only per gli embedding)

### 5c. Ollama (LLM runtime)

Ollama usa l'immagine ufficiale, non richiede build:

```bash
docker compose pull ollama
```

Il modello LLM specificato in `.env` viene scaricato automaticamente al primo `ask.sh`.

### 5d. Verifica finale

Controlla che le immagini siano presenti:

```bash
docker images | grep forensic-rag
```

Output atteso:

```
forensic-rag/whisper     cuda    ...   ~9GB
forensic-rag/ingestion   cpu     ...   ~600MB
```

Il sistema è pronto. Consulta `docs/guida_trascrizione.md` per i comandi operativi (trascrizione, ingestion, query).

### 6. Su VSCode

Installa l'estensione 'WSL'

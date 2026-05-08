# AI SaaS Runbook

## Prerequisites

- Windows with Python 3.14+
- Node.js 20+
- Ollama installed (for Device/Local inference)
- Models pulled:
  - `ollama pull llama3.2:1b`
  - `ollama pull moondream`

## Start Backend

```powershell
cd "d:\python code\AI SaaS\backend"
.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Start Frontend

```powershell
cd "d:\python code\AI SaaS\frontend"
npm run dev
```

Open: `http://127.0.0.1:5173`

## Core Verification

1. Sign up a new user and confirm redirect to chat.
2. Send text prompt in chat.
3. Upload CSV and ask: `analyze this file`.
4. Ask: `create dashboard` with dataset attached.
5. Switch modes:
   - Device (Ollama direct)
   - Local (backend orchestration)
   - Cloud (opt-in only)
6. Generate image in Local/Cloud mode.

## Troubleshooting

- Login loop:
  - Ensure app opened at `127.0.0.1` (not `localhost`).
  - Clear cookies for both hosts once.
- Ollama memory errors:
  - Use smaller model and keep `OLLAMA_NUM_CTX` / `OLLAMA_NUM_BATCH` low.
- Image generation errors:
  - Check free RAM/disk and model cache location on `D:`.


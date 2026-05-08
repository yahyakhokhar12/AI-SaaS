# Multi-AI SaaS Platform

Production-style multi-agent AI SaaS with:
- LLM reasoning (Ollama local + OpenAI-compatible fallback)
- Image generation (Stable Diffusion via `diffusers`)
- File analysis (CSV, Excel, PDF)
- Power BI artifact generation and optional REST automation
- Zero-trust local encrypted chat history (IndexedDB + AES-GCM)

## Architecture

### Backend (`FastAPI`)
- `backend/app/agents/router.py`: intent routing (`LLM`, `image`, `file`, `powerbi`) with keyword + sentence-transformer semantic classification
- `backend/app/services/llm.py`: streaming LLM service (Ollama primary, API fallback)
- `backend/app/services/image.py`: Stable Diffusion image generation
- `backend/app/services/file.py`: CSV/Excel/PDF parsing + analysis
- `backend/app/services/powerbi.py`: dataset prep, DAX generation, dashboard schema, optional Power BI REST upload/export
- `backend/app/services/orchestrator.py`: module orchestration layer for sync + streaming chat
- `backend/app/services/export.py`: artifact packaging (`content_base64`)

### Frontend (`React + Vite`)
- `frontend/src/pages/Chat.jsx`: ChatGPT-style streaming chat, local encrypted history, privacy modes
- `frontend/src/components/ChatUI.jsx`: message rendering, artifact download, file/image previews
- `frontend/src/components/FileUpload.jsx`: upload menu for image/file/camera/voice
- `frontend/src/lib/crypto.js`: AES-GCM key generation + encrypt/decrypt (Web Crypto API)
- `frontend/src/lib/storage.js`: IndexedDB storage via LocalForage

## Zero-Trust Guarantees

Backend does **not** store:
- prompts
- assistant responses
- uploaded file contents

Backend only stores auth, billing, and usage counters. Chat history is encrypted and stored locally in browser IndexedDB.

## Setup

## 1) Backend

```powershell
cd "d:\python code\AI SaaS\backend"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Required env highlights in `backend/.env`:
- `LLM_PROVIDER=ollama` (or `openai_compatible`)
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `OPENAI_COMPAT_API_KEY` (for fallback)
- `EMBEDDINGS_PROVIDER=sentence_transformers`
- `EMBEDDINGS_MODEL=sentence-transformers/all-MiniLM-L6-v2`
- `PBI_ENABLE_UPLOAD`, `PBI_ACCESS_TOKEN`, `PBI_WORKSPACE_ID`

## 2) Frontend

```powershell
cd "d:\python code\AI SaaS\frontend"
npm install
npm run dev
```

Frontend uses `frontend/.env`:
- `VITE_API_URL=http://127.0.0.1:8000`
- Open frontend at `http://127.0.0.1:5173` (avoid `localhost`/`127.0.0.1` cookie mismatch)

## Power BI Output Contract

The platform returns:
- `dataset.csv`
- `dax.txt`
- `dashboard_config.json`
- `instructions.txt`

Optional (if configured and available via API):
- exported report file (e.g. PDF)

No fake `.pbix` generation is performed.

## Validation Checklist

- Intent routing works across LLM/image/file/powerbi prompts
- File upload parsing works for `.csv`, `.xlsx/.xls`, `.pdf`
- Image generation returns image artifact
- Power BI artifacts are generated and downloadable
- Streaming chat works in UI
- Local encrypted chat storage works (IndexedDB + AES-GCM)

## Submission Notes

- Runbook: `RUNBOOK.md`
- Requirement audit and smoke-test evidence: `SUBMISSION_REPORT.md`

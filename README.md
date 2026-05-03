# OpenToken

OpenToken is an MVP AI API gateway with a FastAPI backend, SQLite storage, API key management, usage logs, and a simple dashboard.

## Setup

```powershell
conda activate opentoken
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m uvicorn backend.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Core APIs

```text
POST /auth/register
POST /auth/login
GET  /api/me
GET  /api/keys
POST /api/keys
DELETE /api/keys/{id}
POST /api/playground
POST /v1/chat/completions
GET  /api/logs
GET  /api/usage
GET  /health
```

`/v1/chat/completions` uses an OpenAI-compatible request shape and API key Bearer authentication.

# OpenToken

OpenToken is an MVP AI API gateway with FastAPI, SQLite, API keys, usage logs, credits, settings, and a developer console.

## Setup

```powershell
conda activate opentoken
python -m pip install -r requirements.txt
```

Optional environment:

```powershell
Copy-Item .env.example .env
```

## Run

Recommended:

```powershell
python -m backend.main
```

Equivalent uvicorn command:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 18080 --reload
```

Open:

```text
http://127.0.0.1:18080
```

## Provider Mode

Default mode is mock:

```text
GATEWAY_MODE=mock
```

To call DeepSeek through the real gateway path:

```text
GATEWAY_MODE=real
DEEPSEEK_API_KEY=your_key
MOCK_FALLBACK_ENABLED=true
```

## Test

```powershell
pytest -q
```

## Core APIs

```text
POST /auth/register
POST /auth/login
POST /auth/logout
GET  /api/me
GET  /api/keys
POST /api/keys
DELETE /api/keys/{id}
POST /api/playground
POST /v1/chat/completions
GET  /api/logs
GET  /api/activity
GET  /api/usage
GET  /api/credits
POST /api/credits/top-up
GET  /api/settings
PUT  /api/settings
GET  /health
```

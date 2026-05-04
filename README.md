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

## Security And Controls

Passwords are stored with `bcrypt`. Session tokens and API keys are returned once to the client, but only hashes are stored in SQLite.

API key permissions are enforced. Supported examples:

```text
*                  # full access
chat:completions   # can call /v1/chat/completions
usage:read         # read-only scope placeholder
keys:manage        # management scope placeholder
```

The Settings page's `monthly_budget` and `rate_limit_per_minute` are enforced by the gateway before model calls.

## Admin Login

User and admin login paths are separate:

```text
POST /auth/login
POST /admin/login
```

Create the first admin account with the setup token:

```powershell
Invoke-RestMethod http://127.0.0.1:18080/admin/bootstrap `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"email":"admin@example.com","password":"admin-password123","setup_token":"change-me"}'
```

Set a real value in `.env`:

```text
ADMIN_SETUP_TOKEN=replace-this
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
POST /admin/bootstrap
POST /admin/login
GET  /admin/me
GET  /admin/overview
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

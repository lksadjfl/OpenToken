# OpenToken

OpenToken is an MVP AI API gateway with FastAPI, SQLite, API keys, provider routing, usage logs, credits, settings, and a developer/admin console.

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

Foreground mode. Stop it with `Ctrl+C`:

```powershell
python -m backend.main
```

Background mode on Windows. This clears any old process using port `18080`, starts the server, and writes `.server.pid`:

```powershell
.\scripts\start.ps1
```

Stop the background server:

```powershell
.\scripts\stop.ps1
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

Provider routing is database-driven. Users only receive OpenToken API keys. Provider API keys are configured by an admin and encrypted in SQLite with `ENCRYPTION_KEY`.

```text
ENCRYPTION_KEY=replace-this-with-a-long-random-secret
```

On first startup the app seeds a local mock provider and mock routes for:

```text
deepseek-chat
qwen-plus
glm-4
```

To use a real OpenAI-compatible provider such as DeepSeek:

1. Login as admin.
2. Open the Admin page.
3. Create a provider with `type=deepseek` or `type=openai_compatible` and `base_url=https://api.deepseek.com`.
4. Add the provider API key as a provider credential.
5. Create or update a model route, for example `public_model=deepseek-chat` and `provider_model=deepseek-chat`.
6. Users call `/v1/chat/completions` with their OpenToken API key and only pass `model`.

## Security And Controls

Passwords are stored with `bcrypt`. Session tokens and API keys are returned once to the client, but only hashes are stored in SQLite.

Provider API keys are separate from user API keys. Provider keys are encrypted at rest and are never returned by admin APIs or user APIs.

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

On startup, the backend seeds one admin and one demo user from configuration:

```text
SEED_ADMIN_EMAIL=admin@example.com
SEED_ADMIN_PASSWORD=admin-password123
SEED_USER_EMAIL=user@example.com
SEED_USER_PASSWORD=password123
```

Admin accounts cannot be registered from the UI. The `/admin/bootstrap` endpoint is disabled; admin creation is controlled by backend configuration.

Default local login:

```text
Admin: admin@example.com / admin-password123
User:  user@example.com / password123
```

The user Register button remains enabled for normal user accounts.

## Add A Provider Key From The UI

1. Open `http://127.0.0.1:18080`.
2. In the sign-in card, set `Mode` to `Admin`.
3. Login with the seeded admin account.
4. Open `Admin` in the left navigation.
5. In `Provider management`, create a provider:
   `Name=DeepSeek`, `Type=deepseek`, `Base URL=https://api.deepseek.com`, `Status=active`.
6. Copy the provider ID from the provider table.
7. In `Credentials & routes`, enter that provider ID, key name, provider API key, and click `Add credential`.
8. Create a model route:
   `Public model=deepseek-chat`, `Provider ID=<provider id>`, `Provider model=deepseek-chat`, prices, priority, fallback, status.
9. Click `Test` on the route row.
10. Users call `deepseek-chat` through their own OpenToken API key.

## Test

```powershell
pytest -q
```

## Core APIs

```text
POST /auth/register
POST /auth/login
POST /auth/logout
POST /admin/login
GET  /admin/me
GET  /admin/overview
GET  /admin/providers
POST /admin/providers
PUT  /admin/providers/{id}
POST /admin/providers/{id}/credentials
GET  /admin/model-routes
POST /admin/model-routes
PUT  /admin/model-routes/{id}
POST /admin/model-routes/{id}/test
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

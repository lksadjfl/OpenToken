# OpenToken

OpenToken is a FastAPI AI Gateway moving toward a Sub2API-style architecture: platform-managed upstream accounts, channel/model mapping, groups, OpenToken API keys, usage logs, credits, and a Vue admin/user console.

## Recommended Run: Docker Compose

Start Docker Desktop first, then run:

```powershell
docker compose up --build
```

Open:

```text
http://127.0.0.1:18080
```

Services:

```text
frontend  http://127.0.0.1:18080
backend   internal http://backend:8000
postgres  127.0.0.1:15432
redis     127.0.0.1:16379
```

Default seeded accounts:

```text
Admin: admin@example.com / admin-password123
User:  user@example.com / password123
```

Normal users can register from the UI. Admin users are seeded from backend configuration only; `/admin/bootstrap` is disabled.

## Local Backend Dev

```powershell
conda activate opentoken
python -m pip install -r requirements.txt
python -m backend.main
```

The legacy local backend uses `127.0.0.1:18080` and can fall back to SQLite. The main product path is Docker Compose with PostgreSQL and Redis.

If port `18080` is occupied:

```powershell
.\scripts\stop.ps1
```

or start Docker after freeing the port.

## Frontend Dev

```powershell
cd frontend
npm install
npm run dev
```

Vite proxies `/api`, `/auth`, `/admin`, `/v1`, and `/health` to the local backend.

Build:

```powershell
cd frontend
npm run build
```

## Configuration

Copy `.env.example` when running outside Docker:

```powershell
Copy-Item .env.example .env
```

Important variables:

```text
DATABASE_URL=postgresql+psycopg://opentoken:opentoken@127.0.0.1:15432/opentoken
REDIS_URL=redis://127.0.0.1:16379/0
ENCRYPTION_KEY=replace-this-with-a-long-random-secret
SEED_ADMIN_EMAIL=admin@example.com
SEED_ADMIN_PASSWORD=admin-password123
SEED_USER_EMAIL=user@example.com
SEED_USER_PASSWORD=password123
```

Provider credentials are encrypted with `ENCRYPTION_KEY`. Do not reuse the example key in production.

## Gateway Model

Users never receive upstream provider keys. The split is:

```text
User OpenToken API key -> OpenToken gateway -> admin-managed upstream account key -> provider API
```

Core tables:

```text
accounts    upstream provider/account credentials and scheduling metadata
channels    public model mapping and pricing
groups      channel pools and rate settings
api_keys    user-facing OpenToken keys, quotas, IP rules, group binding
usage_logs  requested/upstream model, account/channel/group, tokens, cost, latency
```

Default seed creates a mock account/channel/group, so `deepseek-chat`, `qwen-plus`, and `glm-4` work without a real provider key.

## Add A Provider Key From The UI

1. Open `http://127.0.0.1:18080`.
2. Login in the admin panel with `admin@example.com / admin-password123`.
3. Open `Admin Accounts`.
4. Create an account:
   `platform=openai_compatible`, `base_url=https://api.deepseek.com`, and paste the upstream API key.
5. Add or update model mapping JSON, for example:
   `{"deepseek-chat":"deepseek-chat"}`.
6. Open `Admin Channels`.
7. Create a channel with model mapping/pricing, for example:
   `{"deepseek-chat":"deepseek-chat"}` and `[{"models":["deepseek-chat"],"input_price":0.000001,"output_price":0.000002}]`.
8. Open `Admin Groups`.
9. Create a group and bind the channel ID.
10. Create a user API key bound to that group from `API Keys`.
11. Call `/v1/chat/completions` with the user OpenToken API key.

## Public APIs

User-compatible APIs:

```text
POST /v1/chat/completions
GET  /api/models
GET  /api/logs
GET  /api/usage
GET  /api/keys
POST /api/keys
DELETE /api/keys/{id}
POST /api/playground
GET  /api/credits
POST /api/credits/top-up
GET  /api/settings
PUT  /api/settings
```

Admin APIs:

```text
POST /admin/login
GET  /admin/dashboard
GET  /admin/accounts
POST /admin/accounts
PUT  /admin/accounts/{id}
POST /admin/accounts/{id}/credentials
POST /admin/accounts/{id}/test
POST /admin/accounts/{id}/disable
POST /admin/accounts/{id}/recover
GET  /admin/channels
POST /admin/channels
PUT  /admin/channels/{id}
GET  /admin/groups
POST /admin/groups
PUT  /admin/groups/{id}
GET  /admin/usage-logs
```

Legacy provider/model-route admin APIs are still present for compatibility but the Vue UI uses accounts/channels/groups.

## Tests

```powershell
conda activate opentoken
python -m pytest -q
```

Validated in the `opentoken` conda environment:

```text
7 passed
```

# OpenToken Next Steps Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the current OpenToken repo from a demoable local MVP into a reproducible, safer, easier-to-maintain gateway prototype.

**Architecture:** Keep the current FastAPI + SQLite + static frontend structure, but first fix engineering hygiene and make existing settings real before doing any larger refactor. Prioritize small, verifiable changes: environment hygiene, auth/session hardening, real enforcement of stored settings, then targeted code splits.

**Tech Stack:** FastAPI, SQLite, pytest, bcrypt, static HTML/CSS/JS, uvicorn

---

## Phase 0: Baseline and environment stability

### Task 1: Add repository hygiene files

**Objective:** Stop committing runtime artifacts and document the intended local environment.

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Modify: `README.md`

**Step 1: Create `.gitignore`**

Add:

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
.env
data.db
*.log
```

**Step 2: Create `.env.example`**

Add:

```env
GATEWAY_MODE=mock
MOCK_FALLBACK_ENABLED=true
OPENTOKEN_DB_PATH=./data.db
SESSION_TTL_SECONDS=86400
SESSION_REVOKE_OLD_ON_LOGIN=false
ALLOWED_ORIGINS=http://127.0.0.1:18080,http://localhost:18080
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
PROVIDER_TIMEOUT_SECONDS=20
PROVIDER_RETRIES=1
```

**Step 3: Update `README.md`**

Add explicit sections for:
- Python version used locally
- install command
- run command
- test command
- meaning of `mock` vs `real`
- note that `.env.example` must be copied to `.env`

**Step 4: Verify**

Run:

```bash
git -C /mnt/g/OpenToken/OpenToken status --short
```

Expected:
- New files visible
- No accidental runtime artifacts added by mistake

**Step 5: Commit**

```bash
git add .gitignore .env.example README.md
git commit -m "docs: add repo hygiene and environment template"
```

---

### Task 2: Make the project runnable in a clean environment

**Objective:** Ensure dependencies match the code and tests can run on a fresh machine.

**Files:**
- Modify: `requirements.txt`
- Test: `tests/test_api.py`

**Step 1: Verify required imports used by app and tests**

Current code needs at least:
- `fastapi`
- `uvicorn[standard]`
- `email-validator`
- `httpx`
- `bcrypt`
- `pytest`

**Step 2: Keep `requirements.txt` minimal but correct**

Expected content should stay close to:

```txt
fastapi==0.124.2
uvicorn[standard]==0.38.0
email-validator==2.3.0
httpx==0.28.1
bcrypt==4.3.0
pytest==9.0.2
```

If any missing runtime/test package is discovered during verification, add only that package.

**Step 3: Verify imports**

Run:

```bash
python3 - <<'PY'
import fastapi, uvicorn, httpx, bcrypt, pytest, email_validator
print('ok')
PY
```

Expected: `ok`

**Step 4: Run tests**

Run:

```bash
python3 -m pytest -q
```

Expected: current test suite passes.

**Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: align dependencies with runtime and tests"
```

---

## Phase 1: Turn fake settings into real backend behavior

### Task 3: Enforce API key permissions

**Objective:** Make the stored `permissions` field actually restrict what a key can do.

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/keys.py`
- Modify: `backend/dependencies.py`
- Modify: `backend/gateway.py`
- Test: `tests/test_api.py`

**Step 1: Narrow the accepted permissions values**

In `backend/schemas.py`, replace free-form permission strings with a constrained value set for MVP, for example:

```python
from typing import Literal

class ApiKeyIn(BaseModel):
    name: str = "default-key"
    permissions: Literal["All", "Chat"] = "All"
```

**Step 2: Add a helper to enforce key scope**

In `backend/dependencies.py`, add a small helper:

```python
def require_key_permission(key_row: dict[str, Any], required: str) -> None:
    permission = (key_row.get("permissions") or "").strip()
    if permission == "All":
        return
    if permission != required:
        raise HTTPException(status_code=403, detail="API key lacks permission")
```

**Step 3: Apply the check in chat completions**

In `backend/gateway.py`, before provider execution for `/v1/chat/completions`, enforce `Chat` permission for key-based access.

**Step 4: Add tests**

Add one test that:
- creates a `Chat` key and succeeds
- creates a non-chat/limited key if retained, or verifies rejection path for unsupported permission

If using only `All` and `Chat`, test that a valid `Chat` key still works.

**Step 5: Verify**

Run:

```bash
python3 -m pytest -q tests/test_api.py -v
```

Expected: permission behavior covered and passing.

**Step 6: Commit**

```bash
git add backend/schemas.py backend/keys.py backend/dependencies.py backend/gateway.py tests/test_api.py
git commit -m "feat: enforce API key permissions"
```

---

### Task 4: Enforce monthly budget before request execution

**Objective:** Make `monthly_budget` meaningful instead of stored-only.

**Files:**
- Modify: `backend/gateway.py`
- Modify: `backend/usage.py` (only if a helper response needs updating)
- Test: `tests/test_api.py`

**Step 1: Add a small spend lookup in `backend/gateway.py`**

Query the current month spend for the user from `logs`.

**Step 2: Add a budget check helper**

Use current stored `monthly_budget` from `user_settings` and reject the request if spend is already at or above budget.

For MVP, keep it simple:
- no forecasting
- no soft warning state
- hard reject once current-month spend >= budget

**Step 3: Return a clear API error**

Example:

```python
raise HTTPException(status_code=402, detail={
    "code": "monthly_budget_exceeded",
    "message": "monthly budget exceeded",
})
```

**Step 4: Add test coverage**

Add a test that:
- sets a very small budget
- inserts or creates enough usage to exceed it
- verifies the next request is rejected

**Step 5: Verify**

Run:

```bash
python3 -m pytest -q tests/test_api.py -v
```

Expected: budget enforcement covered and passing.

**Step 6: Commit**

```bash
git add backend/gateway.py tests/test_api.py
git commit -m "feat: enforce monthly budget in gateway"
```

---

### Task 5: Reject session tokens safely after expiry and stop storing raw session secrets

**Objective:** Improve session security to match API key handling more closely.

**Files:**
- Modify: `backend/db.py`
- Modify: `backend/security.py`
- Modify: `backend/auth.py`
- Modify: `backend/dependencies.py`
- Test: `tests/test_api.py`

**Step 1: Add a session token hashing helper**

In `backend/security.py`, reuse `hash_secret()` for session tokens.

**Step 2: Store hashed session tokens**

In `backend/auth.py`, when creating a session:
- generate raw token
- hash it before insert
- return raw token to the client

**Step 3: Read sessions by hashed token**

In `backend/dependencies.py` and logout handlers, hash the incoming bearer token before querying/updating the database.

**Step 4: Preserve migration simplicity**

For MVP, reuse the existing `token` column rather than adding a second one, unless schema migration becomes awkward. Keep the change surgical.

**Step 5: Add regression tests**

Add tests for:
- login still works
- logout revokes hashed session correctly
- expired session returns 401

**Step 6: Verify**

Run:

```bash
python3 -m pytest -q tests/test_api.py -v
```

Expected: session flow still passes, including logout and expiry checks.

**Step 7: Commit**

```bash
git add backend/db.py backend/security.py backend/auth.py backend/dependencies.py tests/test_api.py
git commit -m "feat: hash stored session tokens"
```

---

## Phase 2: Tighten correctness and accounting

### Task 6: Make usage logging and balance updates transactional

**Objective:** Prevent partial writes where logs and balance diverge.

**Files:**
- Modify: `backend/db.py`
- Modify: `backend/gateway.py`
- Test: `tests/test_api.py`

**Step 1: Add a transaction-friendly DB helper**

In `backend/db.py`, add a small helper that passes a live connection into a callback or exposes a `connect()` context that callers can use directly.

**Step 2: Use one transaction in `create_completion()`**

Inside `backend/gateway.py`, wrap:
- log insert
- balance update

in a single DB transaction.

**Step 3: Add a pre-deduction balance check**

Before updating balance, explicitly reject requests from users with no remaining balance.

**Step 4: Add tests**

Add at least one test covering insufficient balance returning `402`.

**Step 5: Verify**

Run:

```bash
python3 -m pytest -q tests/test_api.py -v
```

Expected: no regression, insufficient-balance path covered.

**Step 6: Commit**

```bash
git add backend/db.py backend/gateway.py tests/test_api.py
git commit -m "fix: make usage accounting transactional"
```

---

### Task 7: Preserve structured request content in logs

**Objective:** Keep useful audit/debug data without overhauling the schema.

**Files:**
- Modify: `backend/db.py`
- Modify: `backend/gateway.py`
- Test: `tests/test_api.py`

**Step 1: Add a new `prompt_json` column to `logs`**

In `backend/db.py`, extend `logs` table migration with:

```sql
prompt_json TEXT
```

using `ensure_column()`.

**Step 2: Save original messages structure**

In `backend/gateway.py`, serialize `payload.messages` into `prompt_json` while keeping the current plain-text `prompt` field for list views.

**Step 3: Add a basic test**

Verify that a log entry is created and the structured prompt field is populated.

**Step 4: Verify**

Run:

```bash
python3 -m pytest -q tests/test_api.py -v
```

Expected: logs still work and structured payload is stored.

**Step 5: Commit**

```bash
git add backend/db.py backend/gateway.py tests/test_api.py
git commit -m "feat: store structured prompt payload in logs"
```

---

## Phase 3: Improve maintainability with small refactors

### Task 8: Extract gateway policy helpers from `create_completion()`

**Objective:** Reduce the complexity of the main request handler without changing behavior.

**Files:**
- Modify: `backend/gateway.py`
- Test: `tests/test_api.py`

**Step 1: Extract pure helpers**

Split out small functions such as:
- `build_prompt(messages)`
- `enforce_budget(...)`
- `compute_cost(...)`
- `build_completion_response(...)`

**Step 2: Keep routing unchanged**

Do not move code into new modules yet. Keep the refactor local to `backend/gateway.py`.

**Step 3: Verify behavior**

Run:

```bash
python3 -m pytest -q
python3 -m py_compile backend/*.py
```

Expected: tests still pass and syntax is clean.

**Step 4: Commit**

```bash
git add backend/gateway.py
git commit -m "refactor: simplify gateway completion flow"
```

---

### Task 9: Split `static/app.js` by responsibility

**Objective:** Make the frontend easier to change without introducing a framework.

**Files:**
- Create: `static/api.js`
- Create: `static/state.js`
- Create: `static/pages.js`
- Modify: `static/app.js`
- Modify: `static/index.html`

**Step 1: Extract API helpers**

Move `headers()` and `api()` into `static/api.js`.

**Step 2: Extract shared client state**

Move `token`, `currentSettings`, and `lastLogs` state into `static/state.js`.

**Step 3: Extract page loading/render logic**

Move functions like `loadLogs`, `loadUsage`, `loadCredits`, `loadSettings`, and route helpers into `static/pages.js`.

**Step 4: Keep `app.js` as the wiring layer**

Leave `app.js` responsible mainly for button handlers and startup initialization.

**Step 5: Update `index.html` script tags**

Load the new files in dependency order before `app.js`.

**Step 6: Verify manually**

Run the app and check:
- register/login
- create key
- playground request
- logs page
- credits page
- settings save

**Step 7: Commit**

```bash
git add static/api.js static/state.js static/pages.js static/app.js static/index.html
git commit -m "refactor: split frontend app logic by responsibility"
```

---

## Phase 4: Expand confidence with targeted tests

### Task 10: Add explicit negative-path tests

**Objective:** Cover the most important edge cases before adding more features.

**Files:**
- Modify: `tests/test_api.py`

**Step 1: Add tests for auth failures**
- duplicate registration → `409`
- bad password → `401`
- missing bearer token → `401`

**Step 2: Add tests for gateway input failures**
- unsupported model → `400`
- empty messages → `400`
- `stream=true` → `400`

**Step 3: Add tests for policy failures**
- insufficient balance → `402`
- monthly budget exceeded → `402`
- invalid API key → `401`

**Step 4: Verify**

Run:

```bash
python3 -m pytest -q tests/test_api.py -v
```

Expected: negative paths documented and covered.

**Step 5: Commit**

```bash
git add tests/test_api.py
git commit -m "test: cover negative API paths"
```

---

## Recommended execution order

1. Task 1 — repo hygiene
2. Task 2 — runnable environment
3. Task 3 — API key permissions
4. Task 4 — monthly budget enforcement
5. Task 5 — hashed sessions
6. Task 6 — transactional accounting
7. Task 7 — structured logs
8. Task 8 — gateway helper extraction
9. Task 9 — frontend split
10. Task 10 — negative-path tests

## Definition of done

The next-step plan is complete when all of the following are true:
- The repo has `.gitignore` and `.env.example`
- `README.md` can bring up the app from scratch
- `python3 -m pytest -q` passes in a clean environment
- `permissions` and `monthly_budget` are enforced by the backend
- Session tokens are not stored raw in the database
- Usage writes are transactional enough for MVP correctness
- Logs retain original structured prompt data
- `backend/gateway.py` and `static/app.js` are both easier to maintain than before
- The test suite covers the main failure paths, not just the happy path

import hashlib
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data.db"
STATIC_DIR = BASE_DIR / "static"

MODEL_PRICING = {
    "deepseek-chat": {"input": 0.000001, "output": 0.000002},
    "qwen-plus": {"input": 0.0000015, "output": 0.000003},
    "glm-4": {"input": 0.000002, "output": 0.000004},
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OpenToken API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ApiKeyIn(BaseModel):
    name: str = "default-key"
    permissions: str = "All"


class SettingsIn(BaseModel):
    default_model: str = "deepseek-chat"
    monthly_budget: float = Field(default=10.0, ge=0)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    language: str = "English"
    theme: str = "light"


class CreditTopUpIn(BaseModel):
    amount: float = Field(gt=0, le=10000)
    note: str = "manual top-up"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionIn(BaseModel):
    model: str = "deepseek-chat"
    messages: list[ChatMessage]
    stream: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all(query: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(query, args).fetchall()
        return [dict(row) for row in rows]


def fetch_one(query: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(query, args).fetchone()
        return dict(row) if row else None


def execute(query: str, args: tuple[Any, ...] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(query, args)
        conn.commit()
        return int(cur.lastrowid)


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 10.0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                key_hash TEXT,
                key_mask TEXT NOT NULL,
                permissions TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                api_key_id INTEGER,
                model TEXT NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                status TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                tokens INTEGER NOT NULL,
                cost REAL NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL,
                provider TEXT NOT NULL DEFAULT 'mock',
                app TEXT NOT NULL DEFAULT 'Playground',
                usage_type TEXT NOT NULL DEFAULT 'chat.completion',
                finish_reason TEXT NOT NULL DEFAULT 'stop',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(api_key_id) REFERENCES api_keys(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                default_model TEXT NOT NULL,
                monthly_budget REAL NOT NULL,
                rate_limit_per_minute INTEGER NOT NULL,
                language TEXT NOT NULL,
                theme TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        ensure_column(conn, "api_keys", "user_id", "INTEGER")
        ensure_column(conn, "api_keys", "key_hash", "TEXT")
        ensure_column(conn, "logs", "user_id", "INTEGER")
        ensure_column(conn, "logs", "api_key_id", "INTEGER")
        ensure_column(conn, "logs", "input_tokens", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "logs", "output_tokens", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "logs", "cost", "REAL NOT NULL DEFAULT 0")
        ensure_column(conn, "logs", "provider", "TEXT NOT NULL DEFAULT 'mock'")
        ensure_column(conn, "logs", "app", "TEXT NOT NULL DEFAULT 'Playground'")
        ensure_column(conn, "logs", "usage_type", "TEXT NOT NULL DEFAULT 'chat.completion'")
        ensure_column(conn, "logs", "finish_reason", "TEXT NOT NULL DEFAULT 'stop'")
        conn.commit()


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    user = fetch_one(
        """
        SELECT users.* FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (token,),
    )
    if not user:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    return user


def public_models() -> list[dict[str, Any]]:
    return [
        {
            "id": model,
            "input_price": pricing["input"],
            "output_price": pricing["output"],
            "status": "available",
        }
        for model, pricing in MODEL_PRICING.items()
    ]


def api_key_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing API key")
    raw_key = authorization.removeprefix("Bearer ").strip()
    row = fetch_one(
        """
        SELECT api_keys.*, users.balance FROM api_keys
        LEFT JOIN users ON users.id = api_keys.user_id
        WHERE api_keys.key_hash = ? AND api_keys.status = 'Active'
        """,
        (hash_secret(raw_key),),
    )
    if not row:
        raise HTTPException(status_code=401, detail="invalid API key")
    if row.get("balance") is not None and float(row["balance"]) <= 0:
        raise HTTPException(status_code=402, detail="insufficient balance")
    return row


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def build_mock_response(model: str, prompt: str) -> str:
    return f"[Mock:{model}] Received your request: {prompt[:240]}"


def provider_for_model(model: str) -> str:
    if model.startswith("deepseek"):
        return "DeepSeek"
    if model.startswith("qwen"):
        return "Qwen"
    if model.startswith("glm"):
        return "Zhipu"
    return "Mock"


def create_completion(payload: ChatCompletionIn, key_row: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload.stream:
        raise HTTPException(status_code=400, detail="streaming is not implemented in MVP")
    if payload.model not in MODEL_PRICING:
        raise HTTPException(status_code=400, detail="unsupported model")
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages are required")

    prompt = "\n".join(f"{msg.role}: {msg.content}" for msg in payload.messages).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="message content is required")

    started = time.perf_counter()
    response_text = build_mock_response(payload.model, prompt)
    input_tokens = estimate_tokens(prompt)
    output_tokens = estimate_tokens(response_text)
    total_tokens = input_tokens + output_tokens
    pricing = MODEL_PRICING[payload.model]
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
    latency_ms = int((time.perf_counter() - started) * 1000) + 25

    user_id = key_row.get("user_id") if key_row else None
    api_key_id = key_row.get("id") if key_row else None
    execute(
        """
        INSERT INTO logs(user_id, api_key_id, model, prompt, response, status,
                         input_tokens, output_tokens, tokens, cost, latency_ms,
                         provider, app, usage_type, finish_reason, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            api_key_id,
            payload.model,
            prompt,
            response_text,
            "success",
            input_tokens,
            output_tokens,
            total_tokens,
            cost,
            latency_ms,
            provider_for_model(payload.model),
            "Playground" if api_key_id is None else "API",
            "chat.completion",
            "stop",
            utc_now(),
        ),
    )
    if user_id:
        execute("UPDATE users SET balance = MAX(balance - ?, 0) WHERE id = ?", (cost, user_id))

    return {
        "id": f"chatcmpl-{secrets.token_hex(8)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost": round(cost, 8),
            "latency_ms": latency_ms,
        },
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/auth/register")
def register(payload: RegisterIn) -> dict[str, Any]:
    now = utc_now()
    try:
        user_id = execute(
            "INSERT INTO users(email, password_hash, balance, created_at) VALUES(?,?,?,?)",
            (payload.email.lower(), hash_secret(payload.password), 10.0, now),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="email already registered") from None
    token = secrets.token_urlsafe(32)
    execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)", (token, user_id, now))
    return {"token": token, "user": {"id": user_id, "email": payload.email.lower(), "balance": 10.0}}


@app.post("/auth/login")
def login(payload: LoginIn) -> dict[str, Any]:
    user = fetch_one(
        "SELECT * FROM users WHERE email = ? AND password_hash = ?",
        (payload.email.lower(), hash_secret(payload.password)),
    )
    if not user:
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = secrets.token_urlsafe(32)
    execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)", (token, user["id"], utc_now()))
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "balance": user["balance"]}}


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    if authorization and authorization.startswith("Bearer "):
        execute("DELETE FROM sessions WHERE token = ?", (authorization.removeprefix("Bearer ").strip(),))
    return {"ok": True}


@app.get("/api/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"id": user["id"], "email": user["email"], "balance": user["balance"]}


@app.get("/api/models")
def models() -> list[dict[str, Any]]:
    return public_models()


@app.get("/api/keys")
def list_keys(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, name, key_mask, permissions, status, created_at
        FROM api_keys
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user["id"],),
    )


@app.post("/api/keys")
def create_key(payload: ApiKeyIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    raw_key = "ot-" + secrets.token_urlsafe(32)
    key_mask = raw_key[:7] + "..." + raw_key[-4:]
    key_id = execute(
        """
        INSERT INTO api_keys(user_id, name, key_hash, key_mask, permissions, status, created_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            user["id"],
            payload.name.strip() or "default-key",
            hash_secret(raw_key),
            key_mask,
            payload.permissions,
            "Active",
            utc_now(),
        ),
    )
    return {
        "id": key_id,
        "name": payload.name,
        "key": raw_key,
        "key_mask": key_mask,
        "permissions": payload.permissions,
        "status": "Active",
    }


@app.delete("/api/keys/{key_id}")
def delete_key(key_id: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, bool]:
    execute("UPDATE api_keys SET status = 'Revoked' WHERE id = ? AND user_id = ?", (key_id, user["id"]))
    return {"ok": True}


@app.post("/api/playground")
def playground(payload: ChatCompletionIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return create_completion(payload, {"user_id": user["id"], "id": None})


@app.post("/v1/chat/completions")
def chat_completions(payload: ChatCompletionIn, key_row: dict[str, Any] = Depends(api_key_user)) -> dict[str, Any]:
    return create_completion(payload, key_row)


@app.get("/api/logs")
def logs(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, created_at AS date, model, provider, app, input_tokens AS input,
               output_tokens AS output, cost, usage_type, latency_ms AS speed,
               finish_reason, prompt, response, status
        FROM logs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (user["id"],),
    )


@app.get("/api/activity")
def activity(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT model,
               COUNT(*) AS requests,
               COALESCE(SUM(tokens), 0) AS tokens,
               COALESCE(SUM(cost), 0) AS spend
        FROM logs
        WHERE user_id = ?
        GROUP BY model
        ORDER BY spend DESC
        """,
        (user["id"],),
    )
    totals = fetch_one(
        """
        SELECT COUNT(*) AS requests,
               COALESCE(SUM(tokens), 0) AS tokens,
               COALESCE(SUM(cost), 0) AS spend
        FROM logs
        WHERE user_id = ?
        """,
        (user["id"],),
    )
    return {"totals": totals or {}, "by_model": rows}


@app.get("/api/usage")
def usage(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT COUNT(*) AS request_count,
               COALESCE(SUM(input_tokens), 0) AS input_tokens,
               COALESCE(SUM(output_tokens), 0) AS output_tokens,
               COALESCE(SUM(tokens), 0) AS total_tokens,
               COALESCE(SUM(cost), 0) AS total_cost
        FROM logs
        WHERE user_id = ?
        """,
        (user["id"],),
    )
    fresh_user = fetch_one("SELECT balance FROM users WHERE id = ?", (user["id"],))
    return {
        **(row or {}),
        "balance": fresh_user["balance"] if fresh_user else 0,
    }


@app.get("/api/credits")
def credits(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    fresh_user = fetch_one("SELECT balance FROM users WHERE id = ?", (user["id"],))
    transactions = fetch_all(
        """
        SELECT id, amount, balance_after, note, created_at
        FROM credit_transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 25
        """,
        (user["id"],),
    )
    return {"balance": fresh_user["balance"] if fresh_user else 0, "transactions": transactions}


@app.post("/api/credits/top-up")
def top_up_credits(payload: CreditTopUpIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    execute("UPDATE users SET balance = balance + ? WHERE id = ?", (payload.amount, user["id"]))
    fresh_user = fetch_one("SELECT balance FROM users WHERE id = ?", (user["id"],))
    balance = fresh_user["balance"] if fresh_user else 0
    transaction_id = execute(
        """
        INSERT INTO credit_transactions(user_id, amount, balance_after, note, created_at)
        VALUES(?,?,?,?,?)
        """,
        (user["id"], payload.amount, balance, payload.note.strip() or "manual top-up", utc_now()),
    )
    return {"id": transaction_id, "amount": payload.amount, "balance": balance}


@app.get("/api/settings")
def get_settings(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    settings = fetch_one("SELECT * FROM user_settings WHERE user_id = ?", (user["id"],))
    if settings:
        return {
            "default_model": settings["default_model"],
            "monthly_budget": settings["monthly_budget"],
            "rate_limit_per_minute": settings["rate_limit_per_minute"],
            "language": settings["language"],
            "theme": settings["theme"],
            "updated_at": settings["updated_at"],
        }
    return {
        "default_model": "deepseek-chat",
        "monthly_budget": 10.0,
        "rate_limit_per_minute": 60,
        "language": "English",
        "theme": "light",
        "updated_at": None,
    }


@app.put("/api/settings")
def save_settings(payload: SettingsIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if payload.default_model not in MODEL_PRICING:
        raise HTTPException(status_code=400, detail="unsupported default model")
    now = utc_now()
    execute(
        """
        INSERT INTO user_settings(user_id, default_model, monthly_budget,
                                  rate_limit_per_minute, language, theme, updated_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            default_model = excluded.default_model,
            monthly_budget = excluded.monthly_budget,
            rate_limit_per_minute = excluded.rate_limit_per_minute,
            language = excluded.language,
            theme = excluded.theme,
            updated_at = excluded.updated_at
        """,
        (
            user["id"],
            payload.default_model,
            payload.monthly_budget,
            payload.rate_limit_per_minute,
            payload.language,
            payload.theme,
            now,
        ),
    )
    return {**payload.model_dump(), "updated_at": now}


@app.get("/{asset_name}")
def static_asset(asset_name: str, request: Request) -> FileResponse:
    if asset_name not in {"app.js", "styles.css"}:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(STATIC_DIR / asset_name)

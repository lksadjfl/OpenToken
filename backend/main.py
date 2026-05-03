import hashlib
import secrets
import sqlite3
import time
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


app = FastAPI(title="OpenToken API", version="0.1.0")
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
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(api_key_id) REFERENCES api_keys(id)
            )
            """
        )
        conn.commit()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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
                         input_tokens, output_tokens, tokens, cost, latency_ms, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
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


@app.get("/api/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"id": user["id"], "email": user["email"], "balance": user["balance"]}


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
        SELECT id, model, prompt, response, status, input_tokens, output_tokens,
               tokens, cost, latency_ms, created_at
        FROM logs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (user["id"],),
    )


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


@app.get("/{asset_name}")
def static_asset(asset_name: str, request: Request) -> FileResponse:
    if asset_name not in {"app.js", "styles.css"}:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(STATIC_DIR / asset_name)

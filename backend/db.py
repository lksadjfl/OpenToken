import sqlite3
from datetime import datetime, timezone
from typing import Any

from .config import DB_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
        return int(cur.lastrowid or 0)


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
                role TEXT NOT NULL DEFAULT 'user',
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
                revoked_at TEXT,
                expires_at TEXT NOT NULL DEFAULT '2099-01-01T00:00:00Z',
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
                error_code TEXT,
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
        ensure_column(conn, "sessions", "revoked_at", "TEXT")
        ensure_column(conn, "sessions", "expires_at", "TEXT NOT NULL DEFAULT '2099-01-01T00:00:00Z'")
        ensure_column(conn, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
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
        ensure_column(conn, "logs", "error_code", "TEXT")
        conn.commit()

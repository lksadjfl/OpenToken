import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.engine import Engine

from .config import DATABASE_URL, SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD, SEED_USER_EMAIL, SEED_USER_PASSWORD


metadata = MetaData()
engine: Engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(20), nullable=False, default="user"),
    Column("balance", Float, nullable=False, default=10.0),
    Column("created_at", String(40), nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token", String(128), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("revoked_at", String(40)),
    Column("expires_at", String(40), nullable=False),
    Column("created_at", String(40), nullable=False),
)

api_keys = Table(
    "api_keys",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("group_id", Integer, ForeignKey("groups.id")),
    Column("name", String(100), nullable=False),
    Column("key_hash", String(128)),
    Column("key_mask", String(64), nullable=False),
    Column("permissions", String(255), nullable=False),
    Column("status", String(20), nullable=False),
    Column("quota", Float, nullable=False, default=0),
    Column("quota_used", Float, nullable=False, default=0),
    Column("expires_at", String(40)),
    Column("ip_whitelist", Text, nullable=False, default="[]"),
    Column("ip_blacklist", Text, nullable=False, default="[]"),
    Column("rate_limit_5h", Float, nullable=False, default=0),
    Column("rate_limit_1d", Float, nullable=False, default=0),
    Column("rate_limit_7d", Float, nullable=False, default=0),
    Column("usage_5h", Float, nullable=False, default=0),
    Column("usage_1d", Float, nullable=False, default=0),
    Column("usage_7d", Float, nullable=False, default=0),
    Column("window_5h_start", String(40)),
    Column("window_1d_start", String(40)),
    Column("window_7d_start", String(40)),
    Column("created_at", String(40), nullable=False),
)

accounts = Table(
    "accounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("platform", String(50), nullable=False),
    Column("type", String(50), nullable=False),
    Column("credentials_encrypted", Text, nullable=False),
    Column("base_url", String(500), nullable=False),
    Column("status", String(20), nullable=False, default="active"),
    Column("schedulable", Boolean, nullable=False, default=True),
    Column("priority", Integer, nullable=False, default=50),
    Column("concurrency", Integer, nullable=False, default=3),
    Column("model_mapping", Text, nullable=False, default="{}"),
    Column("error_message", Text),
    Column("rate_limited_until", String(40)),
    Column("last_used_at", String(40)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

channels = Table(
    "channels",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("status", String(20), nullable=False, default="active"),
    Column("restrict_models", Boolean, nullable=False, default=False),
    Column("model_mapping", Text, nullable=False, default="{}"),
    Column("model_pricing", Text, nullable=False, default="[]"),
    Column("billing_model_source", String(30), nullable=False, default="requested"),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

groups = Table(
    "groups",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("status", String(20), nullable=False, default="active"),
    Column("rate_multiplier", Float, nullable=False, default=1.0),
    Column("rpm_limit", Integer, nullable=False, default=0),
    Column("channel_ids", Text, nullable=False, default="[]"),
    Column("fallback_group_id", Integer),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

usage_logs = Table(
    "usage_logs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("api_key_id", Integer, ForeignKey("api_keys.id")),
    Column("account_id", Integer, ForeignKey("accounts.id")),
    Column("channel_id", Integer, ForeignKey("channels.id")),
    Column("group_id", Integer, ForeignKey("groups.id")),
    Column("request_id", String(80), nullable=False),
    Column("model", String(100), nullable=False),
    Column("requested_model", String(100), nullable=False),
    Column("upstream_model", String(100), nullable=False),
    Column("prompt", Text, nullable=False, default=""),
    Column("response", Text, nullable=False, default=""),
    Column("status", String(20), nullable=False),
    Column("input_tokens", Integer, nullable=False, default=0),
    Column("output_tokens", Integer, nullable=False, default=0),
    Column("tokens", Integer, nullable=False, default=0),
    Column("input_cost", Float, nullable=False, default=0),
    Column("output_cost", Float, nullable=False, default=0),
    Column("total_cost", Float, nullable=False, default=0),
    Column("actual_cost", Float, nullable=False, default=0),
    Column("rate_multiplier", Float, nullable=False, default=1.0),
    Column("duration_ms", Integer, nullable=False, default=0),
    Column("provider", String(100), nullable=False, default="mock"),
    Column("app", String(50), nullable=False, default="API"),
    Column("usage_type", String(50), nullable=False, default="chat.completion"),
    Column("finish_reason", String(50), nullable=False, default="stop"),
    Column("error_code", String(100)),
    Column("created_at", String(40), nullable=False),
)

logs = Table(
    "logs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer),
    Column("api_key_id", Integer),
    Column("model", String(100), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("response", Text, nullable=False),
    Column("status", String(20), nullable=False),
    Column("input_tokens", Integer, nullable=False, default=0),
    Column("output_tokens", Integer, nullable=False, default=0),
    Column("tokens", Integer, nullable=False, default=0),
    Column("cost", Float, nullable=False, default=0),
    Column("latency_ms", Integer, nullable=False, default=0),
    Column("provider", String(100), nullable=False, default="mock"),
    Column("provider_model", String(100)),
    Column("route_id", Integer),
    Column("app", String(50), nullable=False, default="Playground"),
    Column("usage_type", String(50), nullable=False, default="chat.completion"),
    Column("finish_reason", String(50), nullable=False, default="stop"),
    Column("error_code", String(100)),
    Column("created_at", String(40), nullable=False),
)

# Legacy compatibility tables kept for old endpoints/tests during the transition.
providers = Table(
    "providers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("type", String(50), nullable=False),
    Column("base_url", String(500), nullable=False),
    Column("status", String(20), nullable=False, default="active"),
    Column("created_at", String(40), nullable=False),
)
provider_credentials = Table(
    "provider_credentials",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("provider_id", Integer, ForeignKey("providers.id"), nullable=False),
    Column("key_name", String(100), nullable=False),
    Column("api_key_encrypted", Text, nullable=False),
    Column("status", String(20), nullable=False, default="active"),
    Column("created_at", String(40), nullable=False),
)
model_routes = Table(
    "model_routes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("public_model", String(100), nullable=False),
    Column("provider_id", Integer, ForeignKey("providers.id"), nullable=False),
    Column("provider_model", String(100), nullable=False),
    Column("input_price", Float, nullable=False, default=0),
    Column("output_price", Float, nullable=False, default=0),
    Column("priority", Integer, nullable=False, default=100),
    Column("fallback_enabled", Boolean, nullable=False, default=True),
    Column("status", String(20), nullable=False, default="active"),
    Column("created_at", String(40), nullable=False),
)

credit_transactions = Table(
    "credit_transactions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("amount", Float, nullable=False),
    Column("balance_after", Float, nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)

user_settings = Table(
    "user_settings",
    metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("default_model", String(100), nullable=False),
    Column("monthly_budget", Float, nullable=False),
    Column("rate_limit_per_minute", Integer, nullable=False),
    Column("language", String(50), nullable=False),
    Column("theme", String(20), nullable=False),
    Column("updated_at", String(40), nullable=False),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_sqlite() -> bool:
    return engine.dialect.name == "sqlite"


def _translate_qmarks(query: str, args: tuple[Any, ...]) -> tuple[str, dict[str, Any]]:
    params = {f"p{i}": arg for i, arg in enumerate(args)}
    index = 0

    def repl(_: re.Match[str]) -> str:
        nonlocal index
        name = f":p{index}"
        index += 1
        return name

    return re.sub(r"\?", repl, query), params


def _result_rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in result.fetchall()]


def _insert_target_has_id(sql: str) -> bool:
    match = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE)
    if not match:
        return False
    table = metadata.tables.get(match.group(1))
    return bool(table is not None and "id" in table.c)


def fetch_all(query: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    sql, params = _translate_qmarks(query, args)
    with engine.begin() as conn:
        result = conn.execute(text(sql), params)
        return _result_rows(result)


def fetch_one(query: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = fetch_all(query, args)
    return rows[0] if rows else None


def execute(query: str, args: tuple[Any, ...] = ()) -> int:
    sql, params = _translate_qmarks(query, args)
    with engine.begin() as conn:
        if (
            not is_sqlite()
            and sql.lstrip().upper().startswith("INSERT")
            and " RETURNING " not in sql.upper()
            and _insert_target_has_id(sql)
        ):
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
            result = conn.execute(text(sql), params)
            row = result.fetchone()
            return int(row[0]) if row else 0
        result = conn.execute(text(sql), params)
        return int(getattr(result, "lastrowid", 0) or 0)


def execute_many(query: str, rows: list[tuple[Any, ...]]) -> None:
    for row in rows:
        execute(query, row)


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def ensure_column(conn: Any, table: str, column: str, definition: str) -> None:
    inspector = inspect(conn)
    columns = {row["name"] for row in inspector.get_columns(table)}
    if column not in columns:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def seed_default_accounts(conn: Any) -> None:
    from .security import hash_password

    now = utc_now()
    if not conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": SEED_ADMIN_EMAIL}).fetchone():
        conn.execute(
            users.insert().values(email=SEED_ADMIN_EMAIL, password_hash=hash_password(SEED_ADMIN_PASSWORD), role="admin", balance=0, created_at=now)
        )
    if not conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": SEED_USER_EMAIL}).fetchone():
        conn.execute(
            users.insert().values(email=SEED_USER_EMAIL, password_hash=hash_password(SEED_USER_PASSWORD), role="user", balance=10, created_at=now)
        )


def seed_default_routes(conn: Any) -> None:
    from .security import encrypt_secret

    now = utc_now()
    if conn.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one():
        return
    account_id = conn.execute(
        accounts.insert().values(
            name="Mock Account",
            platform="mock",
            type="mock",
            credentials_encrypted=encrypt_secret("mock"),
            base_url="mock://local",
            status="active",
            schedulable=True,
            priority=50,
            concurrency=10,
            model_mapping=json_dumps({"deepseek-chat": "deepseek-chat", "qwen-plus": "qwen-plus", "glm-4": "glm-4"}),
            created_at=now,
            updated_at=now,
        )
    ).inserted_primary_key[0]
    channel_id = conn.execute(
        channels.insert().values(
            name="Default Mock Channel",
            status="active",
            restrict_models=False,
            model_mapping=json_dumps({}),
            model_pricing=json_dumps(
                [
                    {"models": ["deepseek-chat"], "input_price": 0.000001, "output_price": 0.000002},
                    {"models": ["qwen-plus"], "input_price": 0.0000015, "output_price": 0.000003},
                    {"models": ["glm-4"], "input_price": 0.000002, "output_price": 0.000004},
                ]
            ),
            billing_model_source="requested",
            created_at=now,
            updated_at=now,
        )
    ).inserted_primary_key[0]
    conn.execute(
        groups.insert().values(
            name="Default",
            status="active",
            rate_multiplier=1.0,
            rpm_limit=60,
            channel_ids=json_dumps([channel_id]),
            created_at=now,
            updated_at=now,
        )
    )
    provider_id = conn.execute(
        providers.insert().values(name="Mock Provider", type="mock", base_url="mock://local", status="active", created_at=now)
    ).inserted_primary_key[0]
    conn.execute(provider_credentials.insert().values(provider_id=provider_id, key_name="local-dev", api_key_encrypted="mock", status="active", created_at=now))
    for public_model, input_price, output_price in [
        ("deepseek-chat", 0.000001, 0.000002),
        ("qwen-plus", 0.0000015, 0.000003),
        ("glm-4", 0.000002, 0.000004),
    ]:
        conn.execute(
            model_routes.insert().values(
                public_model=public_model,
                provider_id=provider_id,
                provider_model=public_model,
                input_price=input_price,
                output_price=output_price,
                priority=100,
                fallback_enabled=True,
                status="active",
                created_at=now,
            )
        )


def migrate_legacy_sqlite(conn: Any) -> None:
    if not is_sqlite():
        return
    additions = {
        "api_keys": [
            ("group_id", "INTEGER"),
            ("quota", "REAL NOT NULL DEFAULT 0"),
            ("quota_used", "REAL NOT NULL DEFAULT 0"),
            ("expires_at", "TEXT"),
            ("ip_whitelist", "TEXT NOT NULL DEFAULT '[]'"),
            ("ip_blacklist", "TEXT NOT NULL DEFAULT '[]'"),
            ("rate_limit_5h", "REAL NOT NULL DEFAULT 0"),
            ("rate_limit_1d", "REAL NOT NULL DEFAULT 0"),
            ("rate_limit_7d", "REAL NOT NULL DEFAULT 0"),
            ("usage_5h", "REAL NOT NULL DEFAULT 0"),
            ("usage_1d", "REAL NOT NULL DEFAULT 0"),
            ("usage_7d", "REAL NOT NULL DEFAULT 0"),
            ("window_5h_start", "TEXT"),
            ("window_1d_start", "TEXT"),
            ("window_7d_start", "TEXT"),
        ],
        "logs": [
            ("provider_model", "TEXT"),
            ("route_id", "INTEGER"),
            ("app", "TEXT NOT NULL DEFAULT 'Playground'"),
            ("usage_type", "TEXT NOT NULL DEFAULT 'chat.completion'"),
            ("finish_reason", "TEXT NOT NULL DEFAULT 'stop'"),
            ("error_code", "TEXT"),
        ],
        "sessions": [
            ("revoked_at", "TEXT"),
            ("expires_at", "TEXT NOT NULL DEFAULT '2099-01-01T00:00:00Z'"),
        ],
    }
    for table, columns in additions.items():
        if not inspect(conn).has_table(table):
            continue
        for column, definition in columns:
            ensure_column(conn, table, column, definition)


def init_db() -> None:
    metadata.create_all(engine)
    with engine.begin() as conn:
        migrate_legacy_sqlite(conn)
        seed_default_accounts(conn)
        seed_default_routes(conn)

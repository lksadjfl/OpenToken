import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("OPENTOKEN_DB_PATH", BASE_DIR / "data.db"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
REDIS_URL = os.getenv("REDIS_URL", "memory://")
STATIC_DIR = Path(os.getenv("STATIC_DIR", BASE_DIR / "frontend" / "dist"))
LEGACY_STATIC_DIR = BASE_DIR / "static"

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
SESSION_REVOKE_OLD_ON_LOGIN = os.getenv("SESSION_REVOKE_OLD_ON_LOGIN", "false").lower() == "true"
ADMIN_SETUP_TOKEN = os.getenv("ADMIN_SETUP_TOKEN", "change-me")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "dev-encryption-key-change-me")
SEED_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com").lower()
SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "admin-password123")
SEED_USER_EMAIL = os.getenv("SEED_USER_EMAIL", "user@example.com").lower()
SEED_USER_PASSWORD = os.getenv("SEED_USER_PASSWORD", "password123")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:18080,http://localhost:18080").split(",")
    if origin.strip()
]

GATEWAY_MODE = os.getenv("GATEWAY_MODE", "mock").lower()
MOCK_FALLBACK_ENABLED = os.getenv("MOCK_FALLBACK_ENABLED", "true").lower() == "true"
PROVIDER_TIMEOUT_SECONDS = float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "20"))
PROVIDER_RETRIES = int(os.getenv("PROVIDER_RETRIES", "1"))

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

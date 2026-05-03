import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("OPENTOKEN_DB_PATH", BASE_DIR / "data.db"))
STATIC_DIR = BASE_DIR / "static"

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
SESSION_REVOKE_OLD_ON_LOGIN = os.getenv("SESSION_REVOKE_OLD_ON_LOGIN", "false").lower() == "true"

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

MODEL_PRICING = {
    "deepseek-chat": {"input": 0.000001, "output": 0.000002, "provider": "deepseek"},
    "qwen-plus": {"input": 0.0000015, "output": 0.000003, "provider": "mock"},
    "glm-4": {"input": 0.000002, "output": 0.000004, "provider": "mock"},
}

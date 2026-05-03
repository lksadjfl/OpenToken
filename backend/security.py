import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from .config import SESSION_TTL_SECONDS


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    # Legacy SHA-256 support lets old local demo accounts fail closed gradually.
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == password_hash


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry() -> str:
    expires = datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
    return expires.isoformat(timespec="seconds").replace("+00:00", "Z")


def mask_secret(value: str, prefix: int = 7, suffix: int = 4) -> str:
    if len(value) <= prefix + suffix:
        return "***"
    return value[:prefix] + "..." + value[-suffix:]


def scrub_sensitive(value: str) -> str:
    return value.replace("Bearer ", "Bearer ***")

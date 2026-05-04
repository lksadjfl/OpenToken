import hashlib
import base64
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from .config import ENCRYPTION_KEY, SESSION_TTL_SECONDS


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


def _encryption_key_bytes() -> bytes:
    return hashlib.sha256(ENCRYPTION_KEY.encode("utf-8")).digest()


def _xor_stream(data: bytes) -> bytes:
    key = _encryption_key_bytes()
    return _xor_stream_with_key(data, key)


def _xor_stream_with_key(data: bytes, key: bytes) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < len(data):
        block = hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        output.extend(block)
        counter += 1
    return bytes(byte ^ mask for byte, mask in zip(data, output))


def encrypt_secret(value: str) -> str:
    key = _encryption_key_bytes()
    nonce = secrets.token_bytes(16)
    cipher_key = hashlib.sha256(key + nonce + b"cipher").digest()
    encrypted = _xor_stream_with_key(value.encode("utf-8"), cipher_key)
    tag = hashlib.sha256(key + nonce + encrypted + b"tag").digest()
    payload = nonce + tag + encrypted
    return "v2:" + base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_secret(value: str) -> str:
    if value.startswith("v2:"):
        payload = base64.urlsafe_b64decode(value[3:].encode("ascii"))
        nonce, tag, encrypted = payload[:16], payload[16:48], payload[48:]
        key = _encryption_key_bytes()
        expected = hashlib.sha256(key + nonce + encrypted + b"tag").digest()
        if not secrets.compare_digest(tag, expected):
            raise ValueError("encrypted secret failed integrity check")
        cipher_key = hashlib.sha256(key + nonce + b"cipher").digest()
        return _xor_stream_with_key(encrypted, cipher_key).decode("utf-8")
    if value.startswith("v1:"):
        encrypted = base64.urlsafe_b64decode(value[3:].encode("ascii"))
        return _xor_stream(encrypted).decode("utf-8")
    return value

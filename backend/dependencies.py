from collections import defaultdict, deque
from time import monotonic
from typing import Any

from fastapi import Header, HTTPException, Request

from .db import execute, fetch_one, utc_now
from .security import hash_secret


RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    user = fetch_one(
        """
        SELECT users.*, sessions.token, sessions.expires_at, sessions.revoked_at
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (hash_secret(token),),
    )
    if not user or user["revoked_at"]:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    if user["expires_at"] <= utc_now():
        execute("UPDATE sessions SET revoked_at = ? WHERE token = ?", (utc_now(), hash_secret(token)))
        raise HTTPException(status_code=401, detail="session expired")
    return user


def current_admin(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = current_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"code": "admin_required", "message": "admin access required"})
    return user


def has_permission(permission_value: str | None, required: str) -> bool:
    if not permission_value:
        return False
    scopes = {scope.strip() for scope in permission_value.split(",") if scope.strip()}
    return "*" in scopes or "All" in scopes or required in scopes


def require_api_key_permission(key_row: dict[str, Any], required: str) -> None:
    if not has_permission(key_row.get("permissions"), required):
        raise HTTPException(status_code=403, detail={"code": "permission_denied", "message": f"missing permission: {required}"})


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
        raise HTTPException(status_code=402, detail={"code": "insufficient_balance", "message": "insufficient balance"})
    return row


def enforce_rate_limit(request: Request, user_id: int | None, limit: int = 60) -> None:
    key = f"{user_id or 'anon'}:{request.client.host if request.client else 'unknown'}"
    now = monotonic()
    bucket = RATE_BUCKETS[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    bucket.append(now)

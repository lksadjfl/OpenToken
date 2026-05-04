import ipaddress
from typing import Any

from fastapi import Header, HTTPException, Request

from .cache import redis_client
from .db import execute, fetch_one, utc_now
from .security import hash_secret


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
        SELECT api_keys.*, users.balance, users.id AS owner_user_id
        FROM api_keys
        LEFT JOIN users ON users.id = api_keys.user_id
        WHERE api_keys.key_hash = ? AND api_keys.status = 'Active'
        """,
        (hash_secret(raw_key),),
    )
    if not row:
        raise HTTPException(status_code=401, detail="invalid API key")
    if row.get("expires_at") and row["expires_at"] <= utc_now():
        raise HTTPException(status_code=401, detail={"code": "api_key_expired", "message": "API key expired"})
    if row.get("balance") is not None and float(row["balance"]) <= 0:
        raise HTTPException(status_code=402, detail={"code": "insufficient_balance", "message": "insufficient balance"})
    return row


def enforce_rate_limit(request: Request, user_id: int | None, limit: int = 60) -> None:
    if limit <= 0:
        return
    key = f"{user_id or 'anon'}:{request.client.host if request.client else 'unknown'}"
    redis_key = f"rate:{key}"
    cache = redis_client()
    count = cache.incr(redis_key)
    if count == 1:
        cache.expire(redis_key, 60)
    if count > limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def _list_from_json(value: Any) -> list[str]:
    import json

    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(json.loads(value))
    except (TypeError, ValueError):
        return []


def enforce_api_key_ip_policy(key_row: dict[str, Any], request: Request) -> None:
    client_ip = request.client.host if request.client else ""
    if not client_ip:
        return
    whitelist = _list_from_json(key_row.get("ip_whitelist"))
    blacklist = _list_from_json(key_row.get("ip_blacklist"))
    if not whitelist and not blacklist:
        return
    try:
        ip_value = ipaddress.ip_address(client_ip)
    except ValueError:
        return
    if blacklist and any(ip_value in ipaddress.ip_network(item, strict=False) for item in blacklist):
        raise HTTPException(status_code=403, detail={"code": "ip_blocked", "message": "IP is blocked for this API key"})
    if whitelist and not any(ip_value in ipaddress.ip_network(item, strict=False) for item in whitelist):
        raise HTTPException(status_code=403, detail={"code": "ip_not_allowed", "message": "IP is not allowed for this API key"})


def enforce_api_key_quota(key_row: dict[str, Any]) -> None:
    quota = float(key_row.get("quota") or 0)
    quota_used = float(key_row.get("quota_used") or 0)
    if quota > 0 and quota_used >= quota:
        raise HTTPException(status_code=402, detail={"code": "quota_exceeded", "message": "API key quota exceeded"})

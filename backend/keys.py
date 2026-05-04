from typing import Any

from fastapi import APIRouter, Depends

from .db import execute, fetch_all, fetch_one, json_dumps, utc_now
from .dependencies import current_user
from .schemas import ApiKeyIn
from .security import hash_secret, mask_secret, new_token


router = APIRouter()


def normalize_permissions(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned in {"All", "*"}:
        return "*"
    if cleaned == "Limited":
        return "chat:completions"
    return cleaned or "chat:completions"


@router.get("/api/keys")
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


@router.post("/api/keys")
def create_key(payload: ApiKeyIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    raw_key = "ot-" + new_token()
    group_id = payload.group_id
    if not group_id:
        default_group = fetch_one("SELECT id FROM groups WHERE status = 'active' ORDER BY id ASC LIMIT 1")
        group_id = default_group["id"] if default_group else None
    key_id = execute(
        """
        INSERT INTO api_keys(user_id, group_id, name, key_hash, key_mask, permissions, status,
                             quota, quota_used, expires_at, ip_whitelist, ip_blacklist,
                             rate_limit_5h, rate_limit_1d, rate_limit_7d,
                             usage_5h, usage_1d, usage_7d, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user["id"],
            group_id,
            payload.name.strip() or "default-key",
            hash_secret(raw_key),
            mask_secret(raw_key),
            normalize_permissions(payload.permissions),
            "Active",
            payload.quota,
            0,
            payload.expires_at,
            json_dumps(payload.ip_whitelist),
            json_dumps(payload.ip_blacklist),
            0,
            0,
            0,
            0,
            0,
            0,
            utc_now(),
        ),
    )
    return {
        "id": key_id,
        "name": payload.name,
        "key": raw_key,
        "key_mask": mask_secret(raw_key),
        "permissions": normalize_permissions(payload.permissions),
        "status": "Active",
    }


@router.delete("/api/keys/{key_id}")
def delete_key(key_id: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, bool]:
    execute("UPDATE api_keys SET status = 'Revoked' WHERE id = ? AND user_id = ?", (key_id, user["id"]))
    return {"ok": True}

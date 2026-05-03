from typing import Any

from fastapi import APIRouter, Depends

from .db import execute, fetch_all, utc_now
from .dependencies import current_user
from .schemas import ApiKeyIn
from .security import hash_secret, mask_secret, new_token


router = APIRouter()


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
    key_id = execute(
        """
        INSERT INTO api_keys(user_id, name, key_hash, key_mask, permissions, status, created_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            user["id"],
            payload.name.strip() or "default-key",
            hash_secret(raw_key),
            mask_secret(raw_key),
            payload.permissions,
            "Active",
            utc_now(),
        ),
    )
    return {
        "id": key_id,
        "name": payload.name,
        "key": raw_key,
        "key_mask": mask_secret(raw_key),
        "permissions": payload.permissions,
        "status": "Active",
    }


@router.delete("/api/keys/{key_id}")
def delete_key(key_id: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, bool]:
    execute("UPDATE api_keys SET status = 'Revoked' WHERE id = ? AND user_id = ?", (key_id, user["id"]))
    return {"ok": True}

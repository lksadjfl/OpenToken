from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .db import execute, fetch_all, fetch_one, utc_now
from .dependencies import current_admin
from .providers import test_route
from .schemas import ModelRouteIn, ModelRouteUpdateIn, ProviderCredentialIn, ProviderIn, ProviderUpdateIn
from .security import encrypt_secret, mask_secret


router = APIRouter()


@router.get("/admin/overview")
def admin_overview(admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    totals = fetch_one(
        """
        SELECT
          (SELECT COUNT(*) FROM users WHERE role = 'user') AS users,
          (SELECT COUNT(*) FROM api_keys) AS api_keys,
          (SELECT COUNT(*) FROM logs) AS logs,
          (SELECT COALESCE(SUM(cost), 0) FROM logs) AS spend
        """
    )
    recent_users = fetch_all(
        "SELECT id, email, role, balance, created_at FROM users ORDER BY id DESC LIMIT 20"
    )
    return {"totals": totals or {}, "recent_users": recent_users}


def serialize_provider(row: dict[str, Any]) -> dict[str, Any]:
    credentials = fetch_all(
        """
        SELECT id, provider_id, key_name, api_key_encrypted, status, created_at
        FROM provider_credentials
        WHERE provider_id = ?
        ORDER BY id DESC
        """,
        (row["id"],),
    )
    safe_credentials = [
        {
            "id": credential["id"],
            "provider_id": credential["provider_id"],
            "key_name": credential["key_name"],
            "key_mask": mask_secret(credential["api_key_encrypted"]),
            "status": credential["status"],
            "created_at": credential["created_at"],
        }
        for credential in credentials
    ]
    return {**row, "credentials": safe_credentials}


@router.get("/admin/providers")
def list_providers(admin: dict[str, Any] = Depends(current_admin)) -> list[dict[str, Any]]:
    rows = fetch_all("SELECT id, name, type, base_url, status, created_at FROM providers ORDER BY id DESC")
    return [serialize_provider(row) for row in rows]


@router.post("/admin/providers")
def create_provider(payload: ProviderIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    provider_id = execute(
        """
        INSERT INTO providers(name, type, base_url, status, created_at)
        VALUES(?,?,?,?,?)
        """,
        (payload.name, payload.type, payload.base_url, payload.status, utc_now()),
    )
    row = fetch_one("SELECT id, name, type, base_url, status, created_at FROM providers WHERE id = ?", (provider_id,))
    return serialize_provider(row or {})


@router.put("/admin/providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderUpdateIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    row = fetch_one("SELECT id FROM providers WHERE id = ?", (provider_id,))
    if not row:
        raise HTTPException(status_code=404, detail={"code": "provider_not_found", "message": "provider not found"})
    current = fetch_one("SELECT name, type, base_url, status FROM providers WHERE id = ?", (provider_id,)) or {}
    execute(
        """
        UPDATE providers
        SET name = ?, type = ?, base_url = ?, status = ?
        WHERE id = ?
        """,
        (
            payload.name if payload.name is not None else current["name"],
            payload.type if payload.type is not None else current["type"],
            payload.base_url if payload.base_url is not None else current["base_url"],
            payload.status if payload.status is not None else current["status"],
            provider_id,
        ),
    )
    updated = fetch_one("SELECT id, name, type, base_url, status, created_at FROM providers WHERE id = ?", (provider_id,))
    return serialize_provider(updated or {})


@router.post("/admin/providers/{provider_id}/credentials")
def create_provider_credential(
    provider_id: int,
    payload: ProviderCredentialIn,
    admin: dict[str, Any] = Depends(current_admin),
) -> dict[str, Any]:
    provider = fetch_one("SELECT id FROM providers WHERE id = ?", (provider_id,))
    if not provider:
        raise HTTPException(status_code=404, detail={"code": "provider_not_found", "message": "provider not found"})
    credential_id = execute(
        """
        INSERT INTO provider_credentials(provider_id, key_name, api_key_encrypted, status, created_at)
        VALUES(?,?,?,?,?)
        """,
        (provider_id, payload.key_name, encrypt_secret(payload.api_key), payload.status, utc_now()),
    )
    row = fetch_one(
        "SELECT id, provider_id, key_name, api_key_encrypted, status, created_at FROM provider_credentials WHERE id = ?",
        (credential_id,),
    )
    return {
        "id": row["id"],
        "provider_id": row["provider_id"],
        "key_name": row["key_name"],
        "key_mask": mask_secret(row["api_key_encrypted"]),
        "status": row["status"],
        "created_at": row["created_at"],
    }


def route_query(where: str = "", args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return fetch_all(
        f"""
        SELECT r.id, r.public_model, r.provider_id, r.provider_model,
               r.input_price, r.output_price, r.priority, r.fallback_enabled,
               r.status, r.created_at, p.name AS provider_name, p.type AS provider_type,
               p.base_url, p.status AS provider_status
        FROM model_routes r
        JOIN providers p ON p.id = r.provider_id
        {where}
        ORDER BY r.public_model ASC, r.priority ASC, r.id ASC
        """,
        args,
    )


@router.get("/admin/model-routes")
def list_model_routes(admin: dict[str, Any] = Depends(current_admin)) -> list[dict[str, Any]]:
    return route_query()


@router.post("/admin/model-routes")
def create_model_route(payload: ModelRouteIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    provider = fetch_one("SELECT id FROM providers WHERE id = ?", (payload.provider_id,))
    if not provider:
        raise HTTPException(status_code=404, detail={"code": "provider_not_found", "message": "provider not found"})
    route_id = execute(
        """
        INSERT INTO model_routes(public_model, provider_id, provider_model, input_price,
                                 output_price, priority, fallback_enabled, status, created_at)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            payload.public_model,
            payload.provider_id,
            payload.provider_model,
            payload.input_price,
            payload.output_price,
            payload.priority,
            1 if payload.fallback_enabled else 0,
            payload.status,
            utc_now(),
        ),
    )
    return route_query("WHERE r.id = ?", (route_id,))[0]


@router.put("/admin/model-routes/{route_id}")
def update_model_route(route_id: int, payload: ModelRouteUpdateIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    current = fetch_one("SELECT * FROM model_routes WHERE id = ?", (route_id,))
    if not current:
        raise HTTPException(status_code=404, detail={"code": "route_not_found", "message": "model route not found"})
    provider_id = payload.provider_id if payload.provider_id is not None else current["provider_id"]
    provider = fetch_one("SELECT id FROM providers WHERE id = ?", (provider_id,))
    if not provider:
        raise HTTPException(status_code=404, detail={"code": "provider_not_found", "message": "provider not found"})
    execute(
        """
        UPDATE model_routes
        SET public_model = ?, provider_id = ?, provider_model = ?, input_price = ?,
            output_price = ?, priority = ?, fallback_enabled = ?, status = ?
        WHERE id = ?
        """,
        (
            payload.public_model if payload.public_model is not None else current["public_model"],
            provider_id,
            payload.provider_model if payload.provider_model is not None else current["provider_model"],
            payload.input_price if payload.input_price is not None else current["input_price"],
            payload.output_price if payload.output_price is not None else current["output_price"],
            payload.priority if payload.priority is not None else current["priority"],
            1 if (payload.fallback_enabled if payload.fallback_enabled is not None else current["fallback_enabled"]) else 0,
            payload.status if payload.status is not None else current["status"],
            route_id,
        ),
    )
    return route_query("WHERE r.id = ?", (route_id,))[0]


@router.post("/admin/model-routes/{route_id}/test")
async def test_model_route(route_id: int, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    rows = route_query("WHERE r.id = ?", (route_id,))
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "route_not_found", "message": "model route not found"})
    return await test_route(rows[0])

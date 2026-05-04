from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .db import execute, fetch_all, fetch_one, json_dumps, json_loads, utc_now
from .dependencies import current_admin
from .providers import call_account, test_route
from .schemas import (
    AccountCredentialIn,
    AccountIn,
    AccountUpdateIn,
    ChannelIn,
    ChannelUpdateIn,
    ChatCompletionIn,
    GroupIn,
    GroupUpdateIn,
    ModelRouteIn,
    ModelRouteUpdateIn,
    ProviderCredentialIn,
    ProviderIn,
    ProviderUpdateIn,
)
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


@router.get("/admin/dashboard")
def admin_dashboard(admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    totals = fetch_one(
        """
        SELECT
          (SELECT COUNT(*) FROM users WHERE role = 'user') AS users,
          (SELECT COUNT(*) FROM api_keys) AS api_keys,
          (SELECT COUNT(*) FROM accounts) AS accounts,
          (SELECT COUNT(*) FROM channels) AS channels,
          (SELECT COUNT(*) FROM groups) AS groups,
          (SELECT COALESCE(SUM(total_cost), 0) FROM usage_logs) AS spend
        """
    )
    return {"totals": totals or {}}


def serialize_account(row: dict[str, Any]) -> dict[str, Any]:
    safe = dict(row)
    safe.pop("credentials_encrypted", None)
    safe["credential_mask"] = mask_secret(row.get("credentials_encrypted") or "")
    safe["model_mapping"] = json_loads(row.get("model_mapping"), {})
    return safe


@router.get("/admin/accounts")
def list_accounts(admin: dict[str, Any] = Depends(current_admin)) -> list[dict[str, Any]]:
    return [serialize_account(row) for row in fetch_all("SELECT * FROM accounts ORDER BY priority ASC, id DESC")]


@router.post("/admin/accounts")
def create_account(payload: AccountIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    now = utc_now()
    account_id = execute(
        """
        INSERT INTO accounts(name, platform, type, credentials_encrypted, base_url, status,
                             schedulable, priority, concurrency, model_mapping, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payload.name,
            payload.platform,
            payload.type,
            encrypt_secret(payload.api_key),
            payload.base_url,
            payload.status,
            payload.schedulable,
            payload.priority,
            payload.concurrency,
            json_dumps(payload.model_mapping),
            now,
            now,
        ),
    )
    return serialize_account(fetch_one("SELECT * FROM accounts WHERE id = ?", (account_id,)) or {})


@router.put("/admin/accounts/{account_id}")
def update_account(account_id: int, payload: AccountUpdateIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    current = fetch_one("SELECT * FROM accounts WHERE id = ?", (account_id,))
    if not current:
        raise HTTPException(status_code=404, detail={"code": "account_not_found", "message": "account not found"})
    encrypted = encrypt_secret(payload.api_key) if payload.api_key is not None else current["credentials_encrypted"]
    execute(
        """
        UPDATE accounts
        SET name = ?, platform = ?, type = ?, credentials_encrypted = ?, base_url = ?, status = ?,
            schedulable = ?, priority = ?, concurrency = ?, model_mapping = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.name if payload.name is not None else current["name"],
            payload.platform if payload.platform is not None else current["platform"],
            payload.type if payload.type is not None else current["type"],
            encrypted,
            payload.base_url if payload.base_url is not None else current["base_url"],
            payload.status if payload.status is not None else current["status"],
            payload.schedulable if payload.schedulable is not None else current["schedulable"],
            payload.priority if payload.priority is not None else current["priority"],
            payload.concurrency if payload.concurrency is not None else current["concurrency"],
            json_dumps(payload.model_mapping) if payload.model_mapping is not None else current["model_mapping"],
            utc_now(),
            account_id,
        ),
    )
    return serialize_account(fetch_one("SELECT * FROM accounts WHERE id = ?", (account_id,)) or {})


@router.post("/admin/accounts/{account_id}/credentials")
def update_account_credentials(account_id: int, payload: AccountCredentialIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    if not fetch_one("SELECT id FROM accounts WHERE id = ?", (account_id,)):
        raise HTTPException(status_code=404, detail={"code": "account_not_found", "message": "account not found"})
    encrypted = encrypt_secret(payload.api_key)
    execute("UPDATE accounts SET credentials_encrypted = ?, updated_at = ? WHERE id = ?", (encrypted, utc_now(), account_id))
    return {"id": account_id, "credential_mask": mask_secret(encrypted)}


@router.post("/admin/accounts/{account_id}/disable")
def disable_account(account_id: int, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    execute("UPDATE accounts SET status = 'disabled', schedulable = false, updated_at = ? WHERE id = ?", (utc_now(), account_id))
    return serialize_account(fetch_one("SELECT * FROM accounts WHERE id = ?", (account_id,)) or {})


@router.post("/admin/accounts/{account_id}/recover")
def recover_account(account_id: int, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    execute(
        "UPDATE accounts SET status = 'active', schedulable = true, error_message = NULL, rate_limited_until = NULL, updated_at = ? WHERE id = ?",
        (utc_now(), account_id),
    )
    return serialize_account(fetch_one("SELECT * FROM accounts WHERE id = ?", (account_id,)) or {})


@router.post("/admin/accounts/{account_id}/test")
async def test_account(account_id: int, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    account = fetch_one("SELECT * FROM accounts WHERE id = ?", (account_id,))
    if not account:
        raise HTTPException(status_code=404, detail={"code": "account_not_found", "message": "account not found"})
    payload = ChatCompletionIn(model="health-check", messages=[{"role": "user", "content": "ping"}])
    result, latency_ms = await call_account(payload, {**account, "upstream_model": "health-check"}, "health-check")
    return {"ok": True, "account_id": account_id, "latency_ms": latency_ms, "tokens": result.prompt_tokens + result.completion_tokens}


def serialize_channel(row: dict[str, Any]) -> dict[str, Any]:
    safe = dict(row)
    safe["model_mapping"] = json_loads(row.get("model_mapping"), {})
    safe["model_pricing"] = json_loads(row.get("model_pricing"), [])
    return safe


@router.get("/admin/channels")
def list_channels(admin: dict[str, Any] = Depends(current_admin)) -> list[dict[str, Any]]:
    return [serialize_channel(row) for row in fetch_all("SELECT * FROM channels ORDER BY id DESC")]


@router.post("/admin/channels")
def create_channel(payload: ChannelIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    now = utc_now()
    channel_id = execute(
        """
        INSERT INTO channels(name, status, restrict_models, model_mapping, model_pricing,
                             billing_model_source, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            payload.name,
            payload.status,
            payload.restrict_models,
            json_dumps(payload.model_mapping),
            json_dumps(payload.model_pricing),
            payload.billing_model_source,
            now,
            now,
        ),
    )
    return serialize_channel(fetch_one("SELECT * FROM channels WHERE id = ?", (channel_id,)) or {})


@router.put("/admin/channels/{channel_id}")
def update_channel(channel_id: int, payload: ChannelUpdateIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    current = fetch_one("SELECT * FROM channels WHERE id = ?", (channel_id,))
    if not current:
        raise HTTPException(status_code=404, detail={"code": "channel_not_found", "message": "channel not found"})
    execute(
        """
        UPDATE channels
        SET name = ?, status = ?, restrict_models = ?, model_mapping = ?, model_pricing = ?,
            billing_model_source = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.name if payload.name is not None else current["name"],
            payload.status if payload.status is not None else current["status"],
            payload.restrict_models if payload.restrict_models is not None else current["restrict_models"],
            json_dumps(payload.model_mapping) if payload.model_mapping is not None else current["model_mapping"],
            json_dumps(payload.model_pricing) if payload.model_pricing is not None else current["model_pricing"],
            payload.billing_model_source if payload.billing_model_source is not None else current["billing_model_source"],
            utc_now(),
            channel_id,
        ),
    )
    return serialize_channel(fetch_one("SELECT * FROM channels WHERE id = ?", (channel_id,)) or {})


def serialize_group(row: dict[str, Any]) -> dict[str, Any]:
    safe = dict(row)
    safe["channel_ids"] = json_loads(row.get("channel_ids"), [])
    return safe


@router.get("/admin/groups")
def list_groups(admin: dict[str, Any] = Depends(current_admin)) -> list[dict[str, Any]]:
    return [serialize_group(row) for row in fetch_all("SELECT * FROM groups ORDER BY id DESC")]


@router.post("/admin/groups")
def create_group(payload: GroupIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    now = utc_now()
    group_id = execute(
        """
        INSERT INTO groups(name, status, rate_multiplier, rpm_limit, channel_ids,
                           fallback_group_id, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            payload.name,
            payload.status,
            payload.rate_multiplier,
            payload.rpm_limit,
            json_dumps(payload.channel_ids),
            payload.fallback_group_id,
            now,
            now,
        ),
    )
    return serialize_group(fetch_one("SELECT * FROM groups WHERE id = ?", (group_id,)) or {})


@router.put("/admin/groups/{group_id}")
def update_group(group_id: int, payload: GroupUpdateIn, admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
    current = fetch_one("SELECT * FROM groups WHERE id = ?", (group_id,))
    if not current:
        raise HTTPException(status_code=404, detail={"code": "group_not_found", "message": "group not found"})
    execute(
        """
        UPDATE groups
        SET name = ?, status = ?, rate_multiplier = ?, rpm_limit = ?, channel_ids = ?,
            fallback_group_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.name if payload.name is not None else current["name"],
            payload.status if payload.status is not None else current["status"],
            payload.rate_multiplier if payload.rate_multiplier is not None else current["rate_multiplier"],
            payload.rpm_limit if payload.rpm_limit is not None else current["rpm_limit"],
            json_dumps(payload.channel_ids) if payload.channel_ids is not None else current["channel_ids"],
            payload.fallback_group_id if payload.fallback_group_id is not None else current["fallback_group_id"],
            utc_now(),
            group_id,
        ),
    )
    return serialize_group(fetch_one("SELECT * FROM groups WHERE id = ?", (group_id,)) or {})


@router.get("/admin/usage-logs")
def admin_usage_logs(admin: dict[str, Any] = Depends(current_admin)) -> list[dict[str, Any]]:
    return fetch_all("SELECT * FROM usage_logs ORDER BY id DESC LIMIT 100")


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

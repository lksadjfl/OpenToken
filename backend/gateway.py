import fnmatch
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .cache import redis_client
from .db import execute, fetch_all, fetch_one, json_loads, utc_now
from .dependencies import (
    api_key_user,
    current_user,
    enforce_api_key_ip_policy,
    enforce_api_key_quota,
    enforce_rate_limit,
    require_api_key_permission,
)
from .providers import call_account
from .schemas import ChatCompletionIn


router = APIRouter()


def current_month_spend(user_id: int) -> float:
    usage_row = fetch_one(
        """
        SELECT COALESCE(SUM(total_cost), 0) AS spend
        FROM usage_logs
        WHERE user_id = ? AND substr(created_at, 1, 7) = substr(?, 1, 7)
        """,
        (user_id, utc_now()),
    )
    legacy_row = fetch_one(
        """
        SELECT COALESCE(SUM(cost), 0) AS spend
        FROM logs
        WHERE user_id = ? AND substr(created_at, 1, 7) = substr(?, 1, 7)
        """,
        (user_id, utc_now()),
    )
    return float((usage_row or {}).get("spend") or 0) + float((legacy_row or {}).get("spend") or 0)


def enforce_monthly_budget(user_id: int | None) -> None:
    if not user_id:
        return
    settings = fetch_one("SELECT monthly_budget FROM user_settings WHERE user_id = ?", (user_id,))
    if not settings:
        return
    monthly_budget = float(settings["monthly_budget"])
    if monthly_budget > 0 and current_month_spend(user_id) >= monthly_budget:
        raise HTTPException(status_code=402, detail={"code": "monthly_budget_exceeded", "message": "monthly budget exceeded"})


def enforce_balance(user_id: int | None) -> None:
    if not user_id:
        return
    row = fetch_one("SELECT balance FROM users WHERE id = ?", (user_id,))
    if not row or float(row["balance"]) <= 0:
        raise HTTPException(status_code=402, detail={"code": "insufficient_balance", "message": "insufficient balance"})


def resolve_model(mapping: dict[str, str], requested: str) -> tuple[str, bool]:
    if requested in mapping:
        return mapping[requested], True
    for pattern, target in mapping.items():
        if "*" in pattern and fnmatch.fnmatch(requested, pattern):
            return target, True
    return requested, False


def pricing_for(channel: dict[str, Any], requested: str, upstream: str) -> dict[str, float] | None:
    pricing = json_loads(channel.get("model_pricing"), [])
    for row in pricing:
        models = row.get("models") or []
        if any(fnmatch.fnmatch(requested, item) or fnmatch.fnmatch(upstream, item) for item in models):
            return {
                "input": float(row.get("input_price") or 0),
                "output": float(row.get("output_price") or 0),
            }
    return None


def default_group_id() -> int | None:
    row = fetch_one("SELECT id FROM groups WHERE status = 'active' ORDER BY id ASC LIMIT 1")
    return int(row["id"]) if row else None


def group_for_key(key_row: dict[str, Any] | None) -> dict[str, Any] | None:
    group_id = (key_row or {}).get("group_id") or default_group_id()
    if not group_id:
        return None
    return fetch_one("SELECT * FROM groups WHERE id = ? AND status = 'active'", (group_id,))


def selectable_channels(group: dict[str, Any], requested_model: str) -> list[dict[str, Any]]:
    channel_ids = json_loads(group.get("channel_ids"), [])
    if not channel_ids:
        return []
    placeholders = ",".join("?" for _ in channel_ids)
    rows = fetch_all(f"SELECT * FROM channels WHERE id IN ({placeholders}) AND status = 'active' ORDER BY id ASC", tuple(channel_ids))
    selected: list[dict[str, Any]] = []
    for channel in rows:
        channel_mapping = json_loads(channel.get("model_mapping"), {})
        mapped_model, _ = resolve_model(channel_mapping, requested_model)
        if channel.get("restrict_models") and not pricing_for(channel, requested_model, mapped_model):
            continue
        selected.append({**channel, "mapped_model": mapped_model})
    return selected


def selectable_accounts(upstream_model: str) -> list[dict[str, Any]]:
    now = utc_now()
    rows = fetch_all(
        """
        SELECT *
        FROM accounts
        WHERE status = 'active'
          AND schedulable = true
          AND (rate_limited_until IS NULL OR rate_limited_until <= ?)
        ORDER BY priority ASC, COALESCE(last_used_at, '') ASC, id ASC
        """,
        (now,),
    )
    selected: list[dict[str, Any]] = []
    for account in rows:
        account_mapping = json_loads(account.get("model_mapping"), {})
        account_model, _ = resolve_model(account_mapping, upstream_model)
        if account_mapping and account_model == upstream_model and upstream_model not in account_mapping:
            wildcard_match = any("*" in pattern and fnmatch.fnmatch(upstream_model, pattern) for pattern in account_mapping)
            if not wildcard_match:
                continue
        selected.append({**account, "upstream_model": account_model})
    return selected


def acquire_account_slot(account_id: int, concurrency: int) -> str | None:
    cache = redis_client()
    key = f"account:{account_id}:inflight"
    slot = uuid.uuid4().hex
    if cache.scard(key) >= max(1, concurrency):
        return None
    cache.sadd(key, slot)
    return slot


def release_account_slot(account_id: int, slot: str | None) -> None:
    if slot:
        redis_client().srem(f"account:{account_id}:inflight", slot)


def mark_account_failure(account_id: int, message: str) -> None:
    cooldown_until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(timespec="seconds").replace("+00:00", "Z")
    execute(
        "UPDATE accounts SET error_message = ?, rate_limited_until = ?, updated_at = ? WHERE id = ?",
        (message[:500], cooldown_until, utc_now(), account_id),
    )


def log_success(
    *,
    user_id: int | None,
    api_key_id: int | None,
    group_id: int | None,
    channel: dict[str, Any],
    account: dict[str, Any],
    payload: ChatCompletionIn,
    prompt: str,
    response: str,
    input_tokens: int,
    output_tokens: int,
    total_cost: float,
    actual_cost: float,
    duration_ms: int,
    finish_reason: str,
    app: str,
) -> None:
    now = utc_now()
    total_tokens = input_tokens + output_tokens
    usage_id = execute(
        """
        INSERT INTO usage_logs(user_id, api_key_id, account_id, channel_id, group_id, request_id,
                               model, requested_model, upstream_model, prompt, response, status,
                               input_tokens, output_tokens, tokens, input_cost, output_cost,
                               total_cost, actual_cost, rate_multiplier, duration_ms, provider,
                               app, usage_type, finish_reason, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            api_key_id,
            account["id"],
            channel["id"],
            group_id,
            f"req-{uuid.uuid4().hex}",
            payload.model,
            payload.model,
            account["upstream_model"],
            prompt,
            response,
            "success",
            input_tokens,
            output_tokens,
            total_tokens,
            0,
            0,
            total_cost,
            actual_cost,
            float(channel.get("rate_multiplier") or 1),
            duration_ms,
            account["name"],
            app,
            "chat.completion",
            finish_reason,
            now,
        ),
    )
    execute(
        """
        INSERT INTO logs(user_id, api_key_id, model, prompt, response, status,
                         input_tokens, output_tokens, tokens, cost, latency_ms,
                         provider, provider_model, route_id, app, usage_type, finish_reason, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            api_key_id,
            payload.model,
            prompt,
            response,
            "success",
            input_tokens,
            output_tokens,
            total_tokens,
            total_cost,
            duration_ms,
            account["name"],
            account["upstream_model"],
            usage_id,
            app,
            "chat.completion",
            finish_reason,
            now,
        ),
    )


async def create_completion(
    payload: ChatCompletionIn,
    request: Request,
    key_row: dict[str, Any] | None = None,
    user_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if payload.stream:
        raise HTTPException(status_code=400, detail={"code": "stream_not_implemented", "message": "streaming is not implemented"})
    if not payload.messages:
        raise HTTPException(status_code=400, detail={"code": "messages_required", "message": "messages are required"})

    user_id = (key_row or user_row or {}).get("user_id") or (user_row or {}).get("id")
    api_key_id = (key_row or {}).get("id")
    if key_row:
        require_api_key_permission(key_row, "chat:completions")
        enforce_api_key_ip_policy(key_row, request)
        enforce_api_key_quota(key_row)
    settings = fetch_one("SELECT rate_limit_per_minute FROM user_settings WHERE user_id = ?", (user_id,)) if user_id else None
    limit = int((settings or {}).get("rate_limit_per_minute") or 60)
    group = group_for_key(key_row)
    if group and int(group.get("rpm_limit") or 0) > 0:
        limit = int(group["rpm_limit"])
    enforce_rate_limit(request, user_id, limit)
    enforce_monthly_budget(user_id)
    enforce_balance(user_id)

    prompt = "\n".join(f"{msg.role}: {msg.content}" for msg in payload.messages).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail={"code": "message_content_required", "message": "message content is required"})
    if not group:
        raise HTTPException(status_code=403, detail={"code": "permission_denied", "message": "API key is not assigned to an active group"})

    channels = selectable_channels(group, payload.model)
    if not channels:
        raise HTTPException(status_code=404, detail={"code": "model_unavailable", "message": "no channel available for requested model"})

    last_error: HTTPException | None = None
    for channel in channels:
        accounts = selectable_accounts(channel["mapped_model"])
        for account in accounts:
            pricing = pricing_for(channel, payload.model, account["upstream_model"])
            if channel.get("restrict_models") and not pricing:
                continue
            pricing = pricing or {"input": 0.0, "output": 0.0}
            slot = acquire_account_slot(int(account["id"]), int(account.get("concurrency") or 1))
            if not slot:
                continue
            try:
                result, latency_ms = await call_account(payload, account, account["upstream_model"])
            except HTTPException as exc:
                last_error = exc
                mark_account_failure(int(account["id"]), str(exc.detail))
                release_account_slot(int(account["id"]), slot)
                continue
            release_account_slot(int(account["id"]), slot)

            input_tokens = result.prompt_tokens
            output_tokens = result.completion_tokens
            total_cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) * float(group.get("rate_multiplier") or 1.0)
            actual_cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
            log_success(
                user_id=user_id,
                api_key_id=api_key_id,
                group_id=group["id"],
                channel=channel,
                account=account,
                payload=payload,
                prompt=prompt,
                response=result.content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_cost=total_cost,
                actual_cost=actual_cost,
                duration_ms=latency_ms,
                finish_reason=result.finish_reason,
                app="Playground" if api_key_id is None else "API",
            )
            execute("UPDATE accounts SET last_used_at = ?, error_message = NULL, updated_at = ? WHERE id = ?", (utc_now(), utc_now(), account["id"]))
            if user_id:
                execute("UPDATE users SET balance = CASE WHEN balance - ? < 0 THEN 0 ELSE balance - ? END WHERE id = ?", (total_cost, total_cost, user_id))
            if api_key_id:
                execute("UPDATE api_keys SET quota_used = quota_used + ? WHERE id = ?", (total_cost, api_key_id))
            total_tokens = input_tokens + output_tokens
            return {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "model": payload.model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": result.content}, "finish_reason": result.finish_reason}],
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cost": round(total_cost, 8),
                    "latency_ms": latency_ms,
                    "provider": account["name"],
                    "provider_model": account["upstream_model"],
                    "account_id": account["id"],
                    "channel_id": channel["id"],
                    "group_id": group["id"],
                },
            }

    if last_error:
        raise last_error
    raise HTTPException(status_code=503, detail={"code": "provider_unavailable", "message": "all accounts exhausted"})


@router.post("/api/playground")
async def playground(payload: ChatCompletionIn, request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return await create_completion(payload, request, user_row=user)


@router.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionIn, request: Request, key_row: dict[str, Any] = Depends(api_key_user)) -> dict[str, Any]:
    return await create_completion(payload, request, key_row=key_row)

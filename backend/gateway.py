from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .db import execute, fetch_all, fetch_one, utc_now
from .dependencies import api_key_user, current_user, enforce_rate_limit, require_api_key_permission
from .providers import call_provider
from .schemas import ChatCompletionIn


router = APIRouter()


def current_month_spend(user_id: int) -> float:
    row = fetch_one(
        """
        SELECT COALESCE(SUM(cost), 0) AS spend
        FROM logs
        WHERE user_id = ? AND substr(created_at, 1, 7) = substr(?, 1, 7)
        """,
        (user_id, utc_now()),
    )
    return float((row or {}).get("spend") or 0)


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


def model_routes(public_model: str, include_disabled: bool = False) -> list[dict[str, Any]]:
    status_clause = "" if include_disabled else "AND r.status = 'active' AND p.status = 'active'"
    return fetch_all(
        f"""
        SELECT r.id, r.public_model, r.provider_id, r.provider_model,
               r.input_price, r.output_price, r.priority, r.fallback_enabled,
               r.status, p.name AS provider_name, p.type AS provider_type,
               p.base_url, p.status AS provider_status
        FROM model_routes r
        JOIN providers p ON p.id = r.provider_id
        WHERE r.public_model = ? {status_clause}
        ORDER BY r.priority ASC, r.id ASC
        """,
        (public_model,),
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
    settings = fetch_one("SELECT rate_limit_per_minute FROM user_settings WHERE user_id = ?", (user_id,)) if user_id else None
    enforce_rate_limit(request, user_id, int((settings or {}).get("rate_limit_per_minute") or 60))
    enforce_monthly_budget(user_id)
    enforce_balance(user_id)

    prompt = "\n".join(f"{msg.role}: {msg.content}" for msg in payload.messages).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail={"code": "message_content_required", "message": "message content is required"})

    routes = model_routes(payload.model)
    if not routes:
        has_disabled = model_routes(payload.model, include_disabled=True)
        if has_disabled:
            raise HTTPException(status_code=503, detail={"code": "model_unavailable", "message": "model route is disabled"})
        raise HTTPException(status_code=404, detail={"code": "model_unavailable", "message": "model is not available"})

    last_error: HTTPException | None = None
    selected_route: dict[str, Any] | None = None
    result = None
    latency_ms = 0
    for index, route in enumerate(routes):
        try:
            result, latency_ms, _credential = await call_provider(payload, route)
            selected_route = route
            break
        except HTTPException as exc:
            last_error = exc
            can_fallback = bool(route.get("fallback_enabled")) and index < len(routes) - 1
            if can_fallback:
                continue
            raise
    if result is None or selected_route is None:
        raise last_error or HTTPException(status_code=503, detail={"code": "provider_unavailable", "message": "provider unavailable"})

    input_tokens = result.prompt_tokens
    output_tokens = result.completion_tokens
    total_tokens = input_tokens + output_tokens
    cost = input_tokens * float(selected_route["input_price"]) + output_tokens * float(selected_route["output_price"])
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
            result.content,
            "success",
            input_tokens,
            output_tokens,
            total_tokens,
            cost,
            latency_ms,
            selected_route["provider_name"],
            selected_route["provider_model"],
            selected_route["id"],
            "Playground" if api_key_id is None else "API",
            "chat.completion",
            result.finish_reason,
            utc_now(),
        ),
    )
    if user_id:
        execute("UPDATE users SET balance = MAX(balance - ?, 0) WHERE id = ?", (cost, user_id))
    return {
        "id": f"chatcmpl-{utc_now().replace(':', '').replace('-', '')}",
        "object": "chat.completion",
        "model": payload.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result.content}, "finish_reason": result.finish_reason}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost": round(cost, 8),
            "latency_ms": latency_ms,
            "provider": selected_route["provider_name"],
            "provider_model": selected_route["provider_model"],
            "route_id": selected_route["id"],
        },
    }


@router.post("/api/playground")
async def playground(payload: ChatCompletionIn, request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return await create_completion(payload, request, user_row=user)


@router.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionIn, request: Request, key_row: dict[str, Any] = Depends(api_key_user)) -> dict[str, Any]:
    return await create_completion(payload, request, key_row=key_row)

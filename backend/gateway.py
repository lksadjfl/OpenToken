from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .config import MODEL_PRICING
from .db import execute, fetch_one, utc_now
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


async def create_completion(
    payload: ChatCompletionIn,
    request: Request,
    key_row: dict[str, Any] | None = None,
    user_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if payload.stream:
        raise HTTPException(status_code=400, detail={"code": "stream_not_implemented", "message": "streaming is not implemented"})
    if payload.model not in MODEL_PRICING:
        raise HTTPException(status_code=400, detail={"code": "unsupported_model", "message": "unsupported model"})
    if not payload.messages:
        raise HTTPException(status_code=400, detail={"code": "messages_required", "message": "messages are required"})

    user_id = (key_row or user_row or {}).get("user_id") or (user_row or {}).get("id")
    api_key_id = (key_row or {}).get("id")
    if key_row:
        require_api_key_permission(key_row, "chat:completions")
    settings = fetch_one("SELECT rate_limit_per_minute FROM user_settings WHERE user_id = ?", (user_id,)) if user_id else None
    enforce_rate_limit(request, user_id, int((settings or {}).get("rate_limit_per_minute") or 60))
    enforce_monthly_budget(user_id)

    prompt = "\n".join(f"{msg.role}: {msg.content}" for msg in payload.messages).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail={"code": "message_content_required", "message": "message content is required"})

    result, provider, latency_ms = await call_provider(payload)
    input_tokens = result.prompt_tokens
    output_tokens = result.completion_tokens
    total_tokens = input_tokens + output_tokens
    pricing = MODEL_PRICING[payload.model]
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
    execute(
        """
        INSERT INTO logs(user_id, api_key_id, model, prompt, response, status,
                         input_tokens, output_tokens, tokens, cost, latency_ms,
                         provider, app, usage_type, finish_reason, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            provider,
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
        },
    }


@router.post("/api/playground")
async def playground(payload: ChatCompletionIn, request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return await create_completion(payload, request, user_row=user)


@router.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionIn, request: Request, key_row: dict[str, Any] = Depends(api_key_user)) -> dict[str, Any]:
    return await create_completion(payload, request, key_row=key_row)

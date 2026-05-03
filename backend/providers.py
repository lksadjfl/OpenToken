import asyncio
import time

import httpx
from fastapi import HTTPException

from .config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    GATEWAY_MODE,
    MOCK_FALLBACK_ENABLED,
    MODEL_PRICING,
    PROVIDER_RETRIES,
    PROVIDER_TIMEOUT_SECONDS,
)
from .schemas import ChatCompletionIn, ProviderResult


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def provider_for_model(model: str) -> str:
    return MODEL_PRICING.get(model, {}).get("provider", "mock")


def build_mock_response(model: str, prompt: str) -> ProviderResult:
    content = f"[Mock:{model}] Received your request: {prompt[:240]}"
    return ProviderResult(
        content=content,
        prompt_tokens=estimate_tokens(prompt),
        completion_tokens=estimate_tokens(content),
        finish_reason="stop",
    )


async def call_deepseek(payload: ChatCompletionIn) -> ProviderResult:
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=503, detail="DEEPSEEK_API_KEY is not configured")
    body = {
        "model": payload.model,
        "messages": [message.model_dump() for message in payload.messages],
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    last_error: Exception | None = None
    for attempt in range(PROVIDER_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS) as client:
                response = await client.post(f"{DEEPSEEK_BASE_URL.rstrip('/')}/v1/chat/completions", json=body, headers=headers)
            if response.status_code >= 500 and attempt < PROVIDER_RETRIES:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail={"provider": "deepseek", "status": response.status_code})
            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return ProviderResult(
                content=choice["message"]["content"],
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                finish_reason=choice.get("finish_reason") or "stop",
                raw=data,
            )
        except httpx.TimeoutException as exc:
            last_error = exc
            if attempt < PROVIDER_RETRIES:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < PROVIDER_RETRIES:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
    raise HTTPException(status_code=504, detail={"provider": "deepseek", "error": type(last_error).__name__})


async def call_provider(payload: ChatCompletionIn) -> tuple[ProviderResult, str, int]:
    prompt = "\n".join(f"{msg.role}: {msg.content}" for msg in payload.messages).strip()
    started = time.perf_counter()
    provider = provider_for_model(payload.model)
    if GATEWAY_MODE == "real" and provider == "deepseek":
        try:
            result = await call_deepseek(payload)
        except HTTPException:
            if not MOCK_FALLBACK_ENABLED:
                raise
            result = build_mock_response(payload.model, prompt)
            provider = "mock"
    else:
        result = build_mock_response(payload.model, prompt)
        provider = "mock"
    latency_ms = int((time.perf_counter() - started) * 1000) + 1
    if result.prompt_tokens <= 0:
        result.prompt_tokens = estimate_tokens(prompt)
    if result.completion_tokens <= 0:
        result.completion_tokens = estimate_tokens(result.content)
    return result, provider, latency_ms

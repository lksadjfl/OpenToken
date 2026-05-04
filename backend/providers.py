import asyncio
import time
from typing import Any, Protocol

import httpx
from fastapi import HTTPException

from .config import PROVIDER_RETRIES, PROVIDER_TIMEOUT_SECONDS
from .db import fetch_one, json_loads
from .schemas import ChatCompletionIn, ProviderResult
from .security import decrypt_secret


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def prompt_from_payload(payload: ChatCompletionIn) -> str:
    return "\n".join(f"{msg.role}: {msg.content}" for msg in payload.messages).strip()


def active_credential(provider_id: int) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT id, provider_id, key_name, api_key_encrypted, status, created_at
        FROM provider_credentials
        WHERE provider_id = ? AND status = 'active'
        ORDER BY id ASC
        LIMIT 1
        """,
        (provider_id,),
    )


class ProviderClient(Protocol):
    async def chat_completions(
        self,
        payload: ChatCompletionIn,
        route: dict[str, Any],
        credential: dict[str, Any],
    ) -> ProviderResult:
        ...

    async def health_check(self, provider: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        ...


class MockProvider:
    async def chat_completions(
        self,
        payload: ChatCompletionIn,
        route: dict[str, Any],
        credential: dict[str, Any],
    ) -> ProviderResult:
        prompt = prompt_from_payload(payload)
        content = f"[Mock:{route['provider_model']}] Received your request: {prompt[:240]}"
        return ProviderResult(
            content=content,
            prompt_tokens=estimate_tokens(prompt),
            completion_tokens=estimate_tokens(content),
            finish_reason="stop",
        )

    async def health_check(self, provider: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "provider": provider["name"], "type": provider["type"]}


class OpenAICompatibleProvider:
    async def chat_completions(
        self,
        payload: ChatCompletionIn,
        route: dict[str, Any],
        credential: dict[str, Any],
    ) -> ProviderResult:
        provider_type = route.get("provider_type") or route.get("platform") or "openai_compatible"
        encrypted = credential.get("api_key_encrypted") or credential.get("credentials_encrypted") or ""
        api_key = decrypt_secret(encrypted)
        body = {
            "model": route["provider_model"],
            "messages": [message.model_dump() for message in payload.messages],
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        endpoint = f"{route['base_url'].rstrip('/')}/v1/chat/completions"
        last_error: Exception | None = None
        for attempt in range(PROVIDER_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS) as client:
                    response = await client.post(endpoint, json=body, headers=headers)
                if response.status_code >= 500 and attempt < PROVIDER_RETRIES:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                if response.status_code >= 400:
                    raise HTTPException(
                        status_code=502,
                        detail={"code": "provider_error", "provider": provider_type, "status": response.status_code},
                    )
                data = response.json()
                choice = data["choices"][0]
                usage = data.get("usage", {})
                content = choice.get("message", {}).get("content") or choice.get("text") or ""
                return ProviderResult(
                    content=content,
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
        raise HTTPException(
            status_code=504,
            detail={"code": "provider_timeout", "provider": provider_type, "error": type(last_error).__name__},
        )

    async def health_check(self, provider: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        route = {
            "provider_type": provider["type"],
            "provider_model": "health-check",
            "base_url": provider["base_url"],
        }
        payload = ChatCompletionIn(model="health-check", messages=[{"role": "user", "content": "ping"}])
        result = await self.chat_completions(payload, route, credential)
        return {"ok": True, "provider": provider["name"], "tokens": result.prompt_tokens + result.completion_tokens}


REGISTRY: dict[str, ProviderClient] = {
    "mock": MockProvider(),
    "openai_compatible": OpenAICompatibleProvider(),
    "deepseek": OpenAICompatibleProvider(),
    "qwen": OpenAICompatibleProvider(),
    "glm": OpenAICompatibleProvider(),
}


def client_for(provider_type: str) -> ProviderClient:
    client = REGISTRY.get(provider_type)
    if not client:
        raise HTTPException(status_code=400, detail={"code": "unsupported_provider", "message": "unsupported provider type"})
    return client


async def call_provider(payload: ChatCompletionIn, route: dict[str, Any]) -> tuple[ProviderResult, int, dict[str, Any]]:
    credential = active_credential(int(route["provider_id"]))
    if not credential:
        raise HTTPException(status_code=503, detail={"code": "provider_unavailable", "message": "active provider credential not found"})

    started = time.perf_counter()
    result = await client_for(route["provider_type"]).chat_completions(payload, route, credential)
    latency_ms = int((time.perf_counter() - started) * 1000) + 1
    prompt = prompt_from_payload(payload)
    if result.prompt_tokens <= 0:
        result.prompt_tokens = estimate_tokens(prompt)
    if result.completion_tokens <= 0:
        result.completion_tokens = estimate_tokens(result.content)
    return result, latency_ms, credential


async def call_account(payload: ChatCompletionIn, account: dict[str, Any], upstream_model: str) -> tuple[ProviderResult, int]:
    route = {
        "provider_type": account["platform"],
        "platform": account["platform"],
        "provider_model": upstream_model,
        "base_url": account["base_url"],
    }
    credential = {"credentials_encrypted": account["credentials_encrypted"]}
    started = time.perf_counter()
    result = await client_for(account["platform"]).chat_completions(payload, route, credential)
    latency_ms = int((time.perf_counter() - started) * 1000) + 1
    prompt = prompt_from_payload(payload)
    if result.prompt_tokens <= 0:
        result.prompt_tokens = estimate_tokens(prompt)
    if result.completion_tokens <= 0:
        result.completion_tokens = estimate_tokens(result.content)
    return result, latency_ms


async def test_route(route: dict[str, Any]) -> dict[str, Any]:
    credential = active_credential(int(route["provider_id"]))
    if not credential:
        raise HTTPException(status_code=503, detail={"code": "provider_unavailable", "message": "active provider credential not found"})
    payload = ChatCompletionIn(model=route["public_model"], messages=[{"role": "user", "content": "ping"}])
    result, latency_ms, _ = await call_provider(payload, route)
    return {
        "ok": True,
        "route_id": route["id"],
        "provider": route["provider_name"],
        "provider_model": route["provider_model"],
        "latency_ms": latency_ms,
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.prompt_tokens + result.completion_tokens,
        },
    }

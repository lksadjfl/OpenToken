from typing import Any

from fastapi import APIRouter, Depends

from .db import fetch_all, fetch_one, json_loads
from .dependencies import current_user


router = APIRouter()


@router.get("/api/models")
def models() -> list[dict[str, Any]]:
    rows = fetch_all("SELECT name, model_pricing FROM channels WHERE status = 'active' ORDER BY id ASC")
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        for pricing in json_loads(row.get("model_pricing"), []):
            for model in pricing.get("models") or []:
                if "*" in model:
                    continue
                seen.setdefault(
                    model,
                    {
                        "id": model,
                        "input_price": pricing.get("input_price") or 0,
                        "output_price": pricing.get("output_price") or 0,
                        "provider": row["name"],
                        "provider_model": model,
                        "status": "available",
                    },
                )
    return list(seen.values())


@router.get("/api/logs")
def logs(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, created_at AS date, requested_model AS model, provider, upstream_model AS provider_model,
               account_id, app, input_tokens AS input, output_tokens AS output,
               total_cost AS cost, usage_type, duration_ms AS speed, finish_reason, status
        FROM usage_logs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (user["id"],),
    )


@router.get("/api/activity")
def activity(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT requested_model AS model,
               COUNT(*) AS requests,
               COALESCE(SUM(tokens), 0) AS tokens,
               COALESCE(SUM(total_cost), 0) AS spend
        FROM usage_logs
        WHERE user_id = ?
        GROUP BY requested_model
        ORDER BY spend DESC
        """,
        (user["id"],),
    )
    totals = fetch_one(
        """
        SELECT COUNT(*) AS requests,
               COALESCE(SUM(tokens), 0) AS tokens,
               COALESCE(SUM(total_cost), 0) AS spend
        FROM usage_logs
        WHERE user_id = ?
        """,
        (user["id"],),
    )
    return {"totals": totals or {}, "by_model": rows}


@router.get("/api/usage")
def usage(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT COUNT(*) AS request_count,
               COALESCE(SUM(input_tokens), 0) AS input_tokens,
               COALESCE(SUM(output_tokens), 0) AS output_tokens,
               COALESCE(SUM(tokens), 0) AS total_tokens,
               COALESCE(SUM(total_cost), 0) AS total_cost
        FROM usage_logs
        WHERE user_id = ?
        """,
        (user["id"],),
    )
    fresh_user = fetch_one("SELECT balance FROM users WHERE id = ?", (user["id"],))
    return {**(row or {}), "balance": fresh_user["balance"] if fresh_user else 0}

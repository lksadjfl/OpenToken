from typing import Any

from fastapi import APIRouter, Depends

from .db import fetch_all, fetch_one
from .dependencies import current_user


router = APIRouter()


@router.get("/api/models")
def models() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT r.public_model AS id,
               MIN(r.input_price) AS input_price,
               MIN(r.output_price) AS output_price,
               p.name AS provider,
               r.provider_model,
               'available' AS status
        FROM model_routes r
        JOIN providers p ON p.id = r.provider_id
        WHERE r.status = 'active' AND p.status = 'active'
        GROUP BY r.public_model
        ORDER BY r.public_model
        """
    )


@router.get("/api/logs")
def logs(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, created_at AS date, model, provider, provider_model, route_id, app, input_tokens AS input,
               output_tokens AS output, cost, usage_type, latency_ms AS speed,
               finish_reason, status
        FROM logs
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
        SELECT model,
               COUNT(*) AS requests,
               COALESCE(SUM(tokens), 0) AS tokens,
               COALESCE(SUM(cost), 0) AS spend
        FROM logs
        WHERE user_id = ?
        GROUP BY model
        ORDER BY spend DESC
        """,
        (user["id"],),
    )
    totals = fetch_one(
        """
        SELECT COUNT(*) AS requests,
               COALESCE(SUM(tokens), 0) AS tokens,
               COALESCE(SUM(cost), 0) AS spend
        FROM logs
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
               COALESCE(SUM(cost), 0) AS total_cost
        FROM logs
        WHERE user_id = ?
        """,
        (user["id"],),
    )
    fresh_user = fetch_one("SELECT balance FROM users WHERE id = ?", (user["id"],))
    return {**(row or {}), "balance": fresh_user["balance"] if fresh_user else 0}

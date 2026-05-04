from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .db import execute, fetch_one, utc_now
from .dependencies import current_user
from .schemas import SettingsIn


router = APIRouter()


@router.get("/api/settings")
def get_settings(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    settings = fetch_one("SELECT * FROM user_settings WHERE user_id = ?", (user["id"],))
    if settings:
        return {
            "default_model": settings["default_model"],
            "monthly_budget": settings["monthly_budget"],
            "rate_limit_per_minute": settings["rate_limit_per_minute"],
            "language": settings["language"],
            "theme": settings["theme"],
            "updated_at": settings["updated_at"],
        }
    return {
        "default_model": "deepseek-chat",
        "monthly_budget": 10.0,
        "rate_limit_per_minute": 60,
        "language": "English",
        "theme": "light",
        "updated_at": None,
    }


@router.put("/api/settings")
def save_settings(payload: SettingsIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    model = fetch_one(
        """
        SELECT r.id
        FROM model_routes r
        JOIN providers p ON p.id = r.provider_id
        WHERE r.public_model = ? AND r.status = 'active' AND p.status = 'active'
        LIMIT 1
        """,
        (payload.default_model,),
    )
    if not model:
        raise HTTPException(status_code=400, detail={"code": "unsupported_default_model", "message": "unsupported default model"})
    now = utc_now()
    execute(
        """
        INSERT INTO user_settings(user_id, default_model, monthly_budget,
                                  rate_limit_per_minute, language, theme, updated_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            default_model = excluded.default_model,
            monthly_budget = excluded.monthly_budget,
            rate_limit_per_minute = excluded.rate_limit_per_minute,
            language = excluded.language,
            theme = excluded.theme,
            updated_at = excluded.updated_at
        """,
        (user["id"], payload.default_model, payload.monthly_budget, payload.rate_limit_per_minute, payload.language, payload.theme, now),
    )
    return {**payload.model_dump(), "updated_at": now}

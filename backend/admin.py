from typing import Any

from fastapi import APIRouter, Depends

from .db import fetch_all, fetch_one
from .dependencies import current_admin


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

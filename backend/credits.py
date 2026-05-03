from typing import Any

from fastapi import APIRouter, Depends

from .db import execute, fetch_all, fetch_one, utc_now
from .dependencies import current_user
from .schemas import CreditTopUpIn


router = APIRouter()


@router.get("/api/credits")
def credits(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    fresh_user = fetch_one("SELECT balance FROM users WHERE id = ?", (user["id"],))
    transactions = fetch_all(
        """
        SELECT id, amount, balance_after, note, created_at
        FROM credit_transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 25
        """,
        (user["id"],),
    )
    return {"balance": fresh_user["balance"] if fresh_user else 0, "transactions": transactions}


@router.post("/api/credits/top-up")
def top_up_credits(payload: CreditTopUpIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    execute("UPDATE users SET balance = balance + ? WHERE id = ?", (payload.amount, user["id"]))
    fresh_user = fetch_one("SELECT balance FROM users WHERE id = ?", (user["id"],))
    balance = fresh_user["balance"] if fresh_user else 0
    transaction_id = execute(
        """
        INSERT INTO credit_transactions(user_id, amount, balance_after, note, created_at)
        VALUES(?,?,?,?,?)
        """,
        (user["id"], payload.amount, balance, payload.note.strip() or "manual top-up", utc_now()),
    )
    return {"id": transaction_id, "amount": payload.amount, "balance": balance}

import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from .config import SESSION_REVOKE_OLD_ON_LOGIN
from .db import execute, fetch_one, utc_now
from .dependencies import current_user
from .schemas import LoginIn, RegisterIn
from .security import hash_password, new_token, session_expiry, verify_password


router = APIRouter()


def create_session(user_id: int) -> str:
    if SESSION_REVOKE_OLD_ON_LOGIN:
        execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (utc_now(), user_id))
    token = new_token()
    execute(
        "INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES(?,?,?,?)",
        (token, user_id, session_expiry(), utc_now()),
    )
    return token


@router.post("/auth/register")
def register(payload: RegisterIn) -> dict[str, Any]:
    now = utc_now()
    try:
        user_id = execute(
            "INSERT INTO users(email, password_hash, balance, created_at) VALUES(?,?,?,?)",
            (payload.email.lower(), hash_password(payload.password), 10.0, now),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="email already registered") from None
    token = create_session(user_id)
    return {"token": token, "user": {"id": user_id, "email": payload.email.lower(), "balance": 10.0}}


@router.post("/auth/login")
def login(payload: LoginIn) -> dict[str, Any]:
    user = fetch_one("SELECT * FROM users WHERE email = ?", (payload.email.lower(),))
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = create_session(user["id"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "balance": user["balance"]}}


@router.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    if authorization and authorization.startswith("Bearer "):
        execute("UPDATE sessions SET revoked_at = ? WHERE token = ?", (utc_now(), authorization.removeprefix("Bearer ").strip()))
    return {"ok": True}


@router.post("/auth/logout-all")
def logout_all(user: dict[str, Any] = Depends(current_user)) -> dict[str, bool]:
    execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ?", (utc_now(), user["id"]))
    return {"ok": True}


@router.get("/api/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"id": user["id"], "email": user["email"], "balance": user["balance"]}

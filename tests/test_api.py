import os
import sys
import tempfile
from pathlib import Path

db_file = tempfile.NamedTemporaryFile(delete=False)
db_file.close()
os.environ["OPENTOKEN_DB_PATH"] = db_file.name
os.environ["GATEWAY_MODE"] = "mock"
os.environ["ADMIN_SETUP_TOKEN"] = "test-admin-token"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from backend.main import app
from backend.db import fetch_one


def test_auth_key_gateway_usage_and_credits():
    with TestClient(app) as client:
        reg = client.post("/auth/register", json={"email": "test@example.com", "password": "password123"})
        assert reg.status_code == 200
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        stored_session = fetch_one("SELECT token FROM sessions WHERE user_id = ?", (reg.json()["user"]["id"],))
        assert stored_session["token"] != token

        settings = client.put(
            "/api/settings",
            headers=headers,
            json={
                "default_model": "deepseek-chat",
                "monthly_budget": 10,
                "rate_limit_per_minute": 60,
                "language": "English",
                "theme": "light",
            },
        )
        assert settings.status_code == 200

        topup = client.post("/api/credits/top-up", headers=headers, json={"amount": 5, "note": "test"})
        assert topup.status_code == 200

        key = client.post("/api/keys", headers=headers, json={"name": "ci-key", "permissions": "All"})
        assert key.status_code == 200
        assert key.json()["key"].startswith("ot-")

        chat = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key.json()['key']}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert chat.status_code == 200
        assert chat.json()["usage"]["total_tokens"] > 0

        logs = client.get("/api/logs", headers=headers)
        assert logs.status_code == 200
        assert "provider" in logs.json()[0]

        logout = client.post("/auth/logout", headers=headers)
        assert logout.status_code == 200
        assert client.get("/api/me", headers=headers).status_code == 401


def test_api_key_permissions_are_enforced():
    with TestClient(app) as client:
        reg = client.post("/auth/register", json={"email": "scope-test@example.com", "password": "password123"})
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        key = client.post("/api/keys", headers=headers, json={"name": "read-only", "permissions": "usage:read"})
        assert key.status_code == 200
        chat = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key.json()['key']}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert chat.status_code == 403
        assert chat.json()["detail"]["code"] == "permission_denied"


def test_monthly_budget_is_enforced_after_spend_reaches_limit():
    with TestClient(app) as client:
        reg = client.post("/auth/register", json={"email": "budget-test@example.com", "password": "password123"})
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        settings = client.put(
            "/api/settings",
            headers=headers,
            json={
                "default_model": "deepseek-chat",
                "monthly_budget": 0.000001,
                "rate_limit_per_minute": 60,
                "language": "English",
                "theme": "light",
            },
        )
        assert settings.status_code == 200
        key = client.post("/api/keys", headers=headers, json={"name": "budget-key", "permissions": "chat:completions"})
        assert key.status_code == 200
        first = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key.json()['key']}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert first.status_code == 200
        second = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key.json()['key']}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello again"}]},
        )
        assert second.status_code == 402
        assert second.json()["detail"]["code"] == "monthly_budget_exceeded"


def test_admin_auth_is_separate_from_user_auth():
    with TestClient(app) as client:
        user = client.post("/auth/register", json={"email": "not-admin@example.com", "password": "password123"})
        assert user.status_code == 200
        user_admin_login = client.post("/admin/login", json={"email": "not-admin@example.com", "password": "password123"})
        assert user_admin_login.status_code == 401

        admin = client.post(
            "/admin/bootstrap",
            json={"email": "admin@example.com", "password": "admin-password123", "setup_token": "test-admin-token"},
        )
        assert admin.status_code == 200
        admin_login = client.post("/admin/login", json={"email": "admin@example.com", "password": "admin-password123"})
        assert admin_login.status_code == 200
        overview = client.get("/admin/overview", headers={"Authorization": f"Bearer {admin_login.json()['token']}"})
        assert overview.status_code == 200
        assert "totals" in overview.json()

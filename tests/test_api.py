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
from backend.db import execute, fetch_one, utc_now


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

        bootstrap = client.post(
            "/admin/bootstrap",
            json={"email": "admin@example.com", "password": "admin-password123", "setup_token": "test-admin-token"},
        )
        assert bootstrap.status_code == 410
        assert bootstrap.json()["detail"]["code"] == "admin_bootstrap_disabled"
        admin_login = client.post("/admin/login", json={"email": "admin@example.com", "password": "admin-password123"})
        assert admin_login.status_code == 200
        overview = client.get("/admin/overview", headers={"Authorization": f"Bearer {admin_login.json()['token']}"})
        assert overview.status_code == 200
        assert "totals" in overview.json()

        seeded_user = client.post("/auth/login", json={"email": "user@example.com", "password": "password123"})
        assert seeded_user.status_code == 200


def admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/admin/login", json={"email": "admin@example.com", "password": "admin-password123"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']}"}


def user_api_key(client: TestClient, email: str = "route-user@example.com", permissions: str = "chat:completions") -> str:
    reg = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 200
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    key = client.post("/api/keys", headers=headers, json={"name": "route-key", "permissions": permissions})
    assert key.status_code == 200
    return key.json()["key"]


def test_provider_admin_routes_and_mock_gateway():
    with TestClient(app) as client:
        user = client.post("/auth/register", json={"email": "plain-user@example.com", "password": "password123"})
        assert user.status_code == 200
        assert client.get("/admin/providers", headers={"Authorization": f"Bearer {user.json()['token']}"}).status_code == 403

        headers = admin_headers(client)
        provider = client.post(
            "/admin/providers",
            headers=headers,
            json={"name": "CI Mock", "type": "mock", "base_url": "mock://ci", "status": "active"},
        )
        assert provider.status_code == 200
        provider_id = provider.json()["id"]

        credential = client.post(
            f"/admin/providers/{provider_id}/credentials",
            headers=headers,
            json={"key_name": "primary", "api_key": "super-secret-provider-key", "status": "active"},
        )
        assert credential.status_code == 200
        assert "super-secret-provider-key" not in credential.text
        assert "api_key_encrypted" not in credential.text

        route = client.post(
            "/admin/model-routes",
            headers=headers,
            json={
                "public_model": "ci-mock",
                "provider_id": provider_id,
                "provider_model": "mock-provider-model",
                "input_price": 0.000001,
                "output_price": 0.000002,
                "priority": 1,
                "fallback_enabled": True,
                "status": "active",
            },
        )
        assert route.status_code == 200
        route_id = route.json()["id"]

        test = client.post(f"/admin/model-routes/{route_id}/test", headers=headers)
        assert test.status_code == 200
        assert test.json()["provider_model"] == "mock-provider-model"

        key = user_api_key(client)
        chat = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "ci-mock", "messages": [{"role": "user", "content": "route me"}]},
        )
        assert chat.status_code == 200
        assert chat.json()["usage"]["provider"] == "CI Mock"
        assert chat.json()["usage"]["provider_model"] == "mock-provider-model"
        assert chat.json()["usage"]["route_id"] == route_id

        log = fetch_one("SELECT provider, provider_model, route_id, cost, latency_ms FROM logs WHERE model = ?", ("ci-mock",))
        assert log["provider"] == "CI Mock"
        assert log["provider_model"] == "mock-provider-model"
        assert log["route_id"] == route_id
        assert log["cost"] > 0
        assert log["latency_ms"] > 0


def test_route_and_credential_availability_errors_and_fallback():
    with TestClient(app) as client:
        headers = admin_headers(client)
        disabled_provider = client.post(
            "/admin/providers",
            headers=headers,
            json={"name": "Disabled Credential Provider", "type": "mock", "base_url": "mock://disabled", "status": "active"},
        ).json()
        disabled_credential = client.post(
            f"/admin/providers/{disabled_provider['id']}/credentials",
            headers=headers,
            json={"key_name": "disabled", "api_key": "disabled-key", "status": "disabled"},
        )
        assert disabled_credential.status_code == 200
        unavailable_route = client.post(
            "/admin/model-routes",
            headers=headers,
            json={
                "public_model": "credential-disabled-model",
                "provider_id": disabled_provider["id"],
                "provider_model": "credential-disabled",
                "input_price": 0,
                "output_price": 0,
                "priority": 1,
                "fallback_enabled": False,
                "status": "active",
            },
        )
        assert unavailable_route.status_code == 200

        key = user_api_key(client, "credential-user@example.com")
        unavailable = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "credential-disabled-model", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "provider_unavailable"

        disabled_route = client.put(
            f"/admin/model-routes/{unavailable_route.json()['id']}",
            headers=headers,
            json={"status": "disabled"},
        )
        assert disabled_route.status_code == 200
        disabled = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "credential-disabled-model", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert disabled.status_code == 503
        assert disabled.json()["detail"]["code"] == "model_unavailable"

        fallback_provider = client.post(
            "/admin/providers",
            headers=headers,
            json={"name": "Fallback Mock", "type": "mock", "base_url": "mock://fallback", "status": "active"},
        ).json()
        client.post(
            f"/admin/providers/{fallback_provider['id']}/credentials",
            headers=headers,
            json={"key_name": "active", "api_key": "fallback-key", "status": "active"},
        )
        first = client.post(
            "/admin/model-routes",
            headers=headers,
            json={
                "public_model": "fallback-model",
                "provider_id": disabled_provider["id"],
                "provider_model": "broken-first",
                "input_price": 0,
                "output_price": 0,
                "priority": 1,
                "fallback_enabled": True,
                "status": "active",
            },
        )
        assert first.status_code == 200
        second = client.post(
            "/admin/model-routes",
            headers=headers,
            json={
                "public_model": "fallback-model",
                "provider_id": fallback_provider["id"],
                "provider_model": "working-second",
                "input_price": 0.000001,
                "output_price": 0.000002,
                "priority": 2,
                "fallback_enabled": True,
                "status": "active",
            },
        )
        assert second.status_code == 200
        fallback = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "fallback-model", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert fallback.status_code == 200
        assert fallback.json()["usage"]["provider"] == "Fallback Mock"
        assert fallback.json()["usage"]["provider_model"] == "working-second"


def test_gateway_prechecks_for_permission_balance_and_budget():
    with TestClient(app) as client:
        no_permission_key = user_api_key(client, "no-permission@example.com", permissions="usage:read")
        no_permission = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {no_permission_key}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert no_permission.status_code == 403
        assert no_permission.json()["detail"]["code"] == "permission_denied"

        reg = client.post("/auth/register", json={"email": "no-balance@example.com", "password": "password123"})
        user_id = reg.json()["user"]["id"]
        execute("UPDATE users SET balance = 0 WHERE id = ?", (user_id,))
        key = client.post(
            "/api/keys",
            headers={"Authorization": f"Bearer {reg.json()['token']}"},
            json={"name": "no-balance", "permissions": "chat:completions"},
        ).json()["key"]
        no_balance = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert no_balance.status_code == 402
        assert no_balance.json()["detail"]["code"] == "insufficient_balance"

        budget_user = client.post("/auth/register", json={"email": "budget-route@example.com", "password": "password123"})
        budget_id = budget_user.json()["user"]["id"]
        budget_headers = {"Authorization": f"Bearer {budget_user.json()['token']}"}
        client.put(
            "/api/settings",
            headers=budget_headers,
            json={
                "default_model": "deepseek-chat",
                "monthly_budget": 0.000001,
                "rate_limit_per_minute": 60,
                "language": "English",
                "theme": "light",
            },
        )
        execute(
            """
            INSERT INTO logs(user_id, model, prompt, response, status, tokens, cost, latency_ms, provider, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (budget_id, "deepseek-chat", "x", "y", "success", 1, 1.0, 1, "mock", utc_now()),
        )
        budget_key = client.post(
            "/api/keys",
            headers=budget_headers,
            json={"name": "budget-route", "permissions": "chat:completions"},
        ).json()["key"]
        over_budget = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {budget_key}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert over_budget.status_code == 402
        assert over_budget.json()["detail"]["code"] == "monthly_budget_exceeded"

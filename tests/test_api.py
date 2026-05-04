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


def user_api_key(client: TestClient, email: str = "route-user@example.com", permissions: str = "chat:completions", group_id: int | None = None) -> str:
    reg = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 200
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    payload = {"name": "route-key", "permissions": permissions}
    if group_id:
        payload["group_id"] = group_id
    key = client.post("/api/keys", headers=headers, json=payload)
    assert key.status_code == 200
    return key.json()["key"]


def test_account_channel_group_routes_and_mock_gateway():
    with TestClient(app) as client:
        user = client.post("/auth/register", json={"email": "plain-user@example.com", "password": "password123"})
        assert user.status_code == 200
        assert client.get("/admin/accounts", headers={"Authorization": f"Bearer {user.json()['token']}"}).status_code == 403

        headers = admin_headers(client)
        account = client.post(
            "/admin/accounts",
            headers=headers,
            json={
                "name": "CI Mock",
                "platform": "mock",
                "type": "mock",
                "api_key": "super-secret-provider-key",
                "base_url": "mock://ci",
                "priority": 1,
                "model_mapping": {"ci-mock": "mock-provider-model"},
            },
        )
        assert account.status_code == 200
        account_id = account.json()["id"]
        assert "super-secret-provider-key" not in account.text
        assert "credentials_encrypted" not in account.text

        credential = client.post(
            f"/admin/accounts/{account_id}/credentials",
            headers=headers,
            json={"api_key": "rotated-secret-provider-key"},
        )
        assert credential.status_code == 200
        assert "rotated-secret-provider-key" not in credential.text

        channel = client.post(
            "/admin/channels",
            headers=headers,
            json={
                "name": "CI Channel",
                "restrict_models": True,
                "model_mapping": {"ci-mock": "ci-mock"},
                "model_pricing": [{"models": ["ci-mock"], "input_price": 0.000001, "output_price": 0.000002}],
            },
        )
        assert channel.status_code == 200
        channel_id = channel.json()["id"]
        group = client.post(
            "/admin/groups",
            headers=headers,
            json={"name": "CI Group", "channel_ids": [channel_id], "rpm_limit": 60},
        )
        assert group.status_code == 200
        group_id = group.json()["id"]

        test = client.post(f"/admin/accounts/{account_id}/test", headers=headers)
        assert test.status_code == 200

        key = user_api_key(client, group_id=group_id)
        chat = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "ci-mock", "messages": [{"role": "user", "content": "route me"}]},
        )
        assert chat.status_code == 200
        assert chat.json()["usage"]["provider"] == "CI Mock"
        assert chat.json()["usage"]["provider_model"] == "mock-provider-model"
        assert chat.json()["usage"]["account_id"] == account_id
        assert chat.json()["usage"]["channel_id"] == channel_id

        log = fetch_one("SELECT provider, upstream_model, account_id, channel_id, total_cost, duration_ms FROM usage_logs WHERE model = ?", ("ci-mock",))
        assert log["provider"] == "CI Mock"
        assert log["upstream_model"] == "mock-provider-model"
        assert log["account_id"] == account_id
        assert log["channel_id"] == channel_id
        assert log["total_cost"] > 0
        assert log["duration_ms"] > 0


def test_account_availability_errors_and_fallback():
    with TestClient(app) as client:
        headers = admin_headers(client)
        disabled_account = client.post(
            "/admin/accounts",
            headers=headers,
            json={"name": "Disabled Account", "platform": "mock", "type": "mock", "api_key": "disabled-key", "base_url": "mock://disabled", "status": "disabled", "schedulable": False},
        ).json()
        channel = client.post(
            "/admin/channels",
            headers=headers,
            json={
                "name": "Disabled Only",
                "restrict_models": True,
                "model_mapping": {"credential-disabled-model": "credential-disabled"},
                "model_pricing": [{"models": ["credential-disabled-model"], "input_price": 0, "output_price": 0}],
            },
        )
        assert channel.status_code == 200
        group = client.post("/admin/groups", headers=headers, json={"name": "Disabled Group", "channel_ids": [channel.json()["id"]]}).json()

        key = user_api_key(client, "credential-user@example.com", group_id=group["id"])
        unavailable = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "credential-disabled-model", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "provider_unavailable"

        disabled_channel = client.put(
            f"/admin/channels/{channel.json()['id']}",
            headers=headers,
            json={"status": "disabled"},
        )
        assert disabled_channel.status_code == 200
        disabled = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "credential-disabled-model", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert disabled.status_code == 404
        assert disabled.json()["detail"]["code"] == "model_unavailable"

        broken = client.post(
            "/admin/accounts",
            headers=headers,
            json={"name": "Broken First", "platform": "broken", "type": "api_key", "api_key": "bad", "base_url": "mock://broken", "priority": 1, "model_mapping": {"fallback-model": "broken-first"}},
        )
        assert broken.status_code == 200
        fallback_account = client.post(
            "/admin/accounts",
            headers=headers,
            json={"name": "Fallback Mock", "platform": "mock", "type": "mock", "api_key": "fallback-key", "base_url": "mock://fallback", "priority": 2, "model_mapping": {"fallback-model": "working-second"}},
        )
        assert fallback_account.status_code == 200
        fallback_channel = client.post(
            "/admin/channels",
            headers=headers,
            json={"name": "Fallback Channel", "restrict_models": True, "model_mapping": {"fallback-model": "fallback-model"}, "model_pricing": [{"models": ["fallback-model"], "input_price": 0.000001, "output_price": 0.000002}]},
        ).json()
        fallback_group = client.post("/admin/groups", headers=headers, json={"name": "Fallback Group", "channel_ids": [fallback_channel["id"]]}).json()
        fallback_key = user_api_key(client, "fallback-user@example.com", group_id=fallback_group["id"])
        fallback = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {fallback_key}"},
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
            INSERT INTO logs(user_id, model, prompt, response, status, input_tokens, output_tokens, tokens, cost, latency_ms, provider, app, usage_type, finish_reason, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (budget_id, "deepseek-chat", "x", "y", "success", 1, 1, 2, 1.0, 1, "mock", "API", "chat.completion", "stop", utc_now()),
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

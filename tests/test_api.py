import os
import sys
import tempfile
from pathlib import Path

db_file = tempfile.NamedTemporaryFile(delete=False)
db_file.close()
os.environ["OPENTOKEN_DB_PATH"] = db_file.name
os.environ["GATEWAY_MODE"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from backend.main import app


def test_auth_key_gateway_usage_and_credits():
    with TestClient(app) as client:
        reg = client.post("/auth/register", json={"email": "test@example.com", "password": "password123"})
        assert reg.status_code == 200
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

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

import os
import pathlib
import sys
import tempfile

_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_TMP = tempfile.mkdtemp(prefix="sai-test-")
os.environ.update({
    "DB_PATH": os.path.join(_TMP, "test-app.db"),
    "JWT_SECRET_KEY": "unit-test-secret-key-0123456789abcdef",
    "ADMIN_USER": "admin",
    "ADMIN_PASSWORD": "admin-pass-123",
    "WEBHOOK_SECRET": "whsec-unit-test",
    "RATE_MAX": "1000",
    "RATE_WINDOW": "60",
    "SAI_ALLOW_DEV_MODE": "",
    "FONNTE_TOKEN": "",
    "GROQ_API_KEY": "",
    "SUPABASE_URL": "",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app) as c:
        yield c


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_auth(client):
    r = client.post("/api/v1/auth/login",
                    json={"username": "admin", "password": "admin-pass-123"})
    assert r.status_code == 200, r.text
    return auth_header(r.json()["token"])


@pytest.fixture(scope="session")
def sales1(client, admin_auth):
    return _make_sales(client, admin_auth, "sales1")


@pytest.fixture(scope="session")
def sales2(client, admin_auth):
    return _make_sales(client, admin_auth, "sales2")


def _make_sales(client, admin_auth, username):
    r = client.post("/api/v1/admin/users", headers=admin_auth,
                    json={"username": username, "password": f"{username}-pass-123"})
    assert r.status_code == 200, r.text
    uid = r.json()["data"]["id"]
    r = client.post("/api/v1/auth/login",
                    json={"username": username, "password": f"{username}-pass-123"})
    assert r.status_code == 200, r.text
    return {"id": uid, "username": username, "auth": auth_header(r.json()["token"])}


def webhook_post(client, uid: str, sender: str, message: str, name: str = "Budi"):
    return client.post(f"/webhook/fonnte?uid={uid}&token=whsec-unit-test",
                       json={"sender": sender, "message": message, "name": name})

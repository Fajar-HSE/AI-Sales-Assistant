LOGIN = "/api/v1/auth/login"


def test_login_success(client, admin_auth):
    r = client.post(LOGIN, json={"username": "admin", "password": "admin-pass-123"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "success"
    assert d["token"]
    assert d["user"]["role"] == "admin"


def test_login_wrong_password_vs_unknown_user_identical(client):
    """Anti user-enumeration: keduanya harus respons identik."""
    r1 = client.post(LOGIN, json={"username": "admin", "password": "totally-wrong"})
    r2 = client.post(LOGIN, json={"username": "no-such-user-xyz", "password": "whatever-123"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


def test_login_error_no_internal_leak(client):
    r = client.post(LOGIN, json={"username": "admin", "password": "x"})
    body = r.text.lower()
    for marker in ("pbkdf2", "traceback", "exception", "hashlib", "sqlite"):
        assert marker not in body


def test_me_requires_token(client):
    assert client.get("/api/v1/me").status_code == 401


def test_me_invalid_token_sanitized(client):
    r = client.get("/api/v1/me", headers={"Authorization": "Bearer garbage.token.here"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Token tidak valid"


def test_login_validation_422(client):
    r = client.post(LOGIN, json={"username": "", "password": ""})
    assert r.status_code == 422


def test_change_password_flow(client, admin_auth):
    r = client.post("/api/v1/admin/users", headers=admin_auth,
                    json={"username": "pwuser", "password": "oldpass-123"})
    uid = r.json()["data"]["id"]

    # password lama salah -> ditolak tanpa mengubah apa pun
    r = client.put("/api/v1/me",
                   headers=auth_header_for(client, "pwuser", "oldpass-123"),
                   json={"current_password": "salah-benar-salah", "new_password": "newpass-456"})
    assert r.status_code == 400

    # password lama benar -> berhasil, login pakai password baru
    tok = login(client, "pwuser", "oldpass-123")
    r = client.put("/api/v1/me", headers={"Authorization": f"Bearer {tok}"},
                   json={"current_password": "oldpass-123", "new_password": "newpass-456"})
    assert r.status_code == 200

    assert client.post(LOGIN, json={"username": "pwuser", "password": "oldpass-123"}).status_code == 401
    assert client.post(LOGIN, json={"username": "pwuser", "password": "newpass-456"}).status_code == 200

    # kebersihan: hapus user uji
    client.delete(f"/api/v1/admin/users/{uid}", headers=admin_auth)


def auth_header_for(client, username, password):
    return {"Authorization": f"Bearer {login(client, username, password)}"}


def login(client, username, password):
    r = client.post(LOGIN, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]

def test_non_admin_forbidden(client, sales1):
    r = client.get("/api/v1/admin/users", headers=sales1["auth"])
    assert r.status_code == 403


def test_admin_can_list_users(client, admin_auth):
    r = client.get("/api/v1/admin/users", headers=admin_auth)
    assert r.status_code == 200
    data = r.json()["data"]
    assert any(u["username"] == "admin" for u in data)
    # tidak ada hash password yang bocor
    assert all("password" not in u and "password_hash" not in u for u in data)


def test_create_duplicate_username_409(client, admin_auth):
    body = {"username": "dup-user", "password": "duplicated-123"}
    assert client.post("/api/v1/admin/users", headers=admin_auth, json=body).status_code == 200
    assert client.post("/api/v1/admin/users", headers=admin_auth, json=body).status_code == 409


def test_create_short_password_rejected(client, admin_auth):
    r = client.post("/api/v1/admin/users", headers=admin_auth,
                    json={"username": "shortpw", "password": "short"})
    assert r.status_code == 422


def test_create_invalid_username_rejected(client, admin_auth):
    r = client.post("/api/v1/admin/users", headers=admin_auth,
                    json={"username": "spasi tidak valid", "password": "validpass-123"})
    assert r.status_code == 422


def test_disable_user_blocks_access(client, admin_auth):
    r = client.post("/api/v1/admin/users", headers=admin_auth,
                    json={"username": "disableme", "password": "disable-123"})
    uid = r.json()["data"]["id"]
    tok = client.post("/api/v1/auth/login",
                      json={"username": "disableme", "password": "disable-123"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/v1/me", headers=h).status_code == 200

    assert client.put(f"/api/v1/admin/users/{uid}", headers=admin_auth,
                      json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/me", headers=h).status_code == 403
    assert client.get("/api/v1/customers", headers=h).status_code == 403

    client.delete(f"/api/v1/admin/users/{uid}", headers=admin_auth)


def test_admin_cannot_demote_self(client, admin_auth):
    me = client.get("/api/v1/me", headers=admin_auth).json()["data"]
    r = client.put(f"/api/v1/admin/users/{me['id']}", headers=admin_auth, json={"role": "user"})
    assert r.status_code == 400


def test_admin_cannot_delete_self(client, admin_auth):
    me = client.get("/api/v1/me", headers=admin_auth).json()["data"]
    r = client.delete(f"/api/v1/admin/users/{me['id']}", headers=admin_auth)
    assert r.status_code == 400


def test_delete_user_cleans_data(client, admin_auth, sales1):
    """Hapus user harus ikut menghapus data miliknya (tidak ada yatim piatu)."""
    from tests.conftest import webhook_post
    phone = "628111000001"
    r = webhook_post(client, sales1["id"], phone, "hapus saya nanti ya")
    assert r.status_code == 200

    r = client.post("/api/v1/admin/users", headers=admin_auth,
                    json={"username": "doomed", "password": "doomed-12345"})
    doomed_uid = r.json()["data"]["id"]
    assert client.delete(f"/api/v1/admin/users/{doomed_uid}", headers=admin_auth).status_code == 200
    assert client.delete(f"/api/v1/admin/users/{doomed_uid}", headers=admin_auth).status_code == 404

    # cleanup customer uji milik sales1
    import app.db as db
    db.db_exec("DELETE FROM customers WHERE owner_id=? AND phone=?", (sales1["id"], phone))
    db.db_exec("DELETE FROM chats WHERE owner_id=? AND phone=?", (sales1["id"], phone))

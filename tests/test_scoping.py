from tests.conftest import webhook_post


def test_user_cannot_see_other_users_customers(client, sales1, sales2):
    phone = "628333333003"
    assert webhook_post(client, sales1["id"], phone, "pesan khusus sales1").status_code == 200

    custs1 = client.get("/api/v1/customers", headers=sales1["auth"]).json()
    assert any(c["phone"] == phone for c in custs1)

    # IDOR: sales2 tidak boleh melihat data milik sales1
    custs2 = client.get("/api/v1/customers", headers=sales2["auth"]).json()
    assert not any(c["phone"] == phone for c in custs2)

    msgs = client.get(f"/api/v1/customers/{phone}/messages", headers=sales2["auth"]).json()
    assert msgs["count"] == 0


def test_owner_param_escalation_blocked(client, sales1):
    """User biasa mencoba ?owner=all tetap hanya melihat datanya sendiri."""
    custs = client.get("/api/v1/customers?owner=all", headers=sales1["auth"]).json()
    assert all(c["owner_id"] == sales1["id"] for c in custs)


def test_admin_sees_all_and_specific(client, admin_auth, sales1, sales2):
    p1, p2 = "628444444004", "628555555005"
    webhook_post(client, sales1["id"], p1, "milik sales1")
    webhook_post(client, sales2["id"], p2, "milik sales2")

    allc = client.get("/api/v1/customers?owner=all", headers=admin_auth).json()
    phones = {c["phone"] for c in allc}
    assert {p1, p2}.issubset(phones)

    only1 = client.get(f"/api/v1/customers?owner={sales1['id']}", headers=admin_auth).json()
    assert any(c["phone"] == p1 for c in only1)
    assert not any(c["phone"] == p2 for c in only1)


def test_stats_scoped(client, admin_auth, sales1):
    stats = client.get("/api/v1/stats", headers=sales1["auth"]).json()["data"]
    assert stats["scope"] == sales1["id"]
    assert stats["total"] >= 0
    assert len(stats["activity"]) == 7

    stats_all = client.get("/api/v1/stats?owner=all", headers=admin_auth).json()["data"]
    assert stats_all["scope"] == "all"


def teardown_module():
    import app.db as db
    for phone in ("628333333003", "628444444004", "628555555005"):
        db.db_exec("DELETE FROM customers WHERE phone=?", (phone,))
        db.db_exec("DELETE FROM chats WHERE phone=?", (phone,))

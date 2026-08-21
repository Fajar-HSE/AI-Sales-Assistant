from tests.conftest import webhook_post


def test_webhook_rejects_missing_token(client):
    r = client.post("/webhook/fonnte", json={"sender": "628123", "message": "hai"})
    assert r.status_code == 401


def test_webhook_rejects_wrong_token(client):
    r = client.post("/webhook/fonnte?token=wrong-token",
                    json={"sender": "628123", "message": "hai"})
    assert r.status_code == 401


def test_webhook_accepts_header_token(client, sales1):
    r = client.post(f"/webhook/fonnte?uid={sales1['id']}",
                    headers={"x-webhook-token": "whsec-unit-test"},
                    json={"sender": "628200000001", "message": "halo kak", "name": "Tono"})
    assert r.status_code == 200
    assert r.json()["type"] == "message"


def test_webhook_device_status_skipped(client, sales1):
    r = client.post(f"/webhook/fonnte?uid={sales1['id']}&token=whsec-unit-test",
                    json={"stateid": "connected", "device": "628xxx"})
    assert r.status_code == 200
    assert r.json()["type"] == "device_status"


def test_webhook_invalid_json_sanitized(client, sales1):
    r = client.post(f"/webhook/fonnte?uid={sales1['id']}&token=whsec-unit-test",
                    content=b"{not-json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Payload JSON tidak valid"
    assert "{" not in r.json()["detail"]


def test_webhook_scores_and_scopes_customer(client, sales1, admin_auth):
    phone = "628211111001"
    r = webhook_post(client, sales1["id"], phone, "kak, harga pelatihan K3 berapa?")
    assert r.status_code == 200
    assert r.json() == {"status": "received", "type": "message"}

    # customer tercatat milik sales1 dengan hasil scoring
    custs = client.get("/api/v1/customers", headers=sales1["auth"]).json()
    match = [c for c in custs if c["phone"] == phone]
    assert len(match) == 1
    assert match[0]["owner_id"] == sales1["id"]
    assert isinstance(match[0]["score"], int)
    assert 0 <= match[0]["score"] <= 100
    assert match[0]["category"] in ("Hot Lead", "Warm Lead", "Cold Lead")
    assert match[0]["unread"] >= 1

    # riwayat chat terisi
    msgs = client.get(f"/api/v1/customers/{phone}/messages", headers=sales1["auth"]).json()
    assert msgs["count"] >= 1
    assert any(m["d"].startswith("kak, harga") for m in msgs["data"])

    # cleanup
    import app.db as db
    db.db_exec("DELETE FROM customers WHERE owner_id=? AND phone=?", (sales1["id"], phone))
    db.db_exec("DELETE FROM chats WHERE owner_id=? AND phone=?", (sales1["id"], phone))


def test_ws_broadcast_on_incoming(client, sales1):
    phone = "628222222002"
    with client.websocket_connect("/ws") as ws:
        r = webhook_post(client, sales1["id"], phone, "tes broadcast websocket")
        assert r.status_code == 200
        evt = ws.receive_json()
        assert evt["type"] == "chat_incoming"
        assert evt["owner_id"] == sales1["id"]
        assert evt["customer"]["phone"] == phone

    import app.db as db
    db.db_exec("DELETE FROM customers WHERE owner_id=? AND phone=?", (sales1["id"], phone))
    db.db_exec("DELETE FROM chats WHERE owner_id=? AND phone=?", (sales1["id"], phone))

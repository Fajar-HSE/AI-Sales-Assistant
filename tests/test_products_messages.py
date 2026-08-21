def test_product_crud_scoped(client, sales1, sales2, admin_auth):
    r = client.post("/api/v1/products", headers=sales1["auth"],
                    json={"name": "Sertifikasi POPAL", "category": "BNSP",
                          "price_range": "1.5jt-3jt", "duration": "2 hari"})
    assert r.status_code == 200
    pid = r.json()["product_id"]

    # owner bisa lihat
    got = client.get(f"/api/v1/products/{pid}", headers=sales1["auth"])
    assert got.status_code == 200
    assert got.json()["name"] == "Sertifikasi POPAL"

    # user lain tidak ikut list (scoping by owner)
    lst2 = client.get("/api/v1/products", headers=sales2["auth"]).json()
    assert not any(p["id"] == pid for p in lst2)

    # admin lihat semua
    lista = client.get("/api/v1/products?owner=all", headers=admin_auth).json()
    assert any(p["id"] == pid for p in lista)

    # 404 untuk id tak dikenal (bukan 200 + status error)
    r = client.get("/api/v1/products/tidak-ada", headers=sales1["auth"])
    assert r.status_code == 404


def test_product_validation(client, sales1):
    r = client.post("/api/v1/products", headers=sales1["auth"], json={"description": "tanpa nama"})
    assert r.status_code == 422


def test_send_message_without_token_records_outgoing(client, sales1):
    """FONNTE_TOKEN kosong -> sent=false tapi chat keluar tetap tercatat."""
    to = "628999888777"
    r = client.post("/api/v1/messages/send", headers=sales1["auth"],
                    json={"to": to, "text": "Terima kasih sudah menghubungi ICC."})
    assert r.status_code == 200
    d = r.json()
    assert d["sent"] is False

    msgs = client.get(f"/api/v1/customers/{to}/messages", headers=sales1["auth"]).json()["data"]
    assert any(m["dir"] == "out" and "ICC" in m["d"] for m in msgs)

    import app.db as db
    db.db_exec("DELETE FROM chats WHERE owner_id=? AND phone=?", (sales1["id"], to))
    db.db_exec("DELETE FROM customers WHERE owner_id=? AND phone=?", (sales1["id"], to))


def test_send_message_validation(client, sales1):
    assert client.post("/api/v1/messages/send", headers=sales1["auth"],
                       json={"to": "", "text": ""}).status_code == 422

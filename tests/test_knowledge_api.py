KB_TEXT = ("Harga pelatihan K3 umum berada pada rentang 1.5 juta hingga 3 juta rupiah per peserta. "
           "Sertifikasi BNSP POPAL mencakup ujian teori dan praktik.")


def test_kb_upload_scoped_and_searchable(client, sales1, sales2, admin_auth):
    r = client.post("/api/v1/knowledge/upload", headers=sales1["auth"],
                    files={"file": ("faq-k3.txt", KB_TEXT.encode(), "text/plain")},
                    data={"category": "BNSP", "name": "FAQ K3"})
    assert r.status_code == 200, r.text
    doc_id = r.json()["doc_id"]
    assert r.json()["chunk_count"] >= 1

    lst = client.get("/api/v1/knowledge", headers=sales1["auth"]).json()["data"]
    assert any(d["id"] == doc_id for d in lst["docs"])

    s = client.get("/api/v1/knowledge/search?q=harga%20pelatihan%20K3",
                   headers=sales1["auth"]).json()["data"]
    assert s["count"] >= 1
    assert any(h["doc_id"] == doc_id for h in s["hits"])

    # user lain TIDAK bisa melihat dokumen itu (owner scoping)
    lst2 = client.get("/api/v1/knowledge", headers=sales2["auth"]).json()["data"]
    assert not any(d["id"] == doc_id for d in lst2["docs"])
    r2 = client.get(f"/api/v1/knowledge/doc/{doc_id}", headers=sales2["auth"])
    assert r2.status_code in (404, 403)

    # admin bisa lihat semua
    lsta = client.get("/api/v1/knowledge?owner=all", headers=admin_auth).json()["data"]
    assert any(d["id"] == doc_id for d in lsta["docs"])

    # update -> re-chunk otomatis
    new_text = KB_TEXT + " Tambahan: kuota kelas terbatas 15 peserta per batch."
    r = client.put(f"/api/v1/knowledge/{doc_id}", headers=sales1["auth"],
                   json={"kb_text": new_text})
    assert r.status_code == 200
    doc = client.get(f"/api/v1/knowledge/doc/{doc_id}", headers=sales1["auth"]).json()["data"]
    assert "kuota kelas" in doc["kb_text"]

    assert client.delete(f"/api/v1/knowledge/{doc_id}", headers=sales1["auth"]).status_code == 200
    assert client.get(f"/api/v1/knowledge/doc/{doc_id}", headers=sales1["auth"]).status_code == 404


def test_kb_invalid_category_falls_back_umum(client, sales1):
    r = client.post("/api/v1/knowledge/upload", headers=sales1["auth"],
                    files={"file": ("x.txt", b"isi dokumen uji", "text/plain")},
                    data={"category": "Nonsense"})
    assert r.status_code == 200
    doc_id = r.json()["doc_id"]
    doc = client.get(f"/api/v1/knowledge/doc/{doc_id}", headers=sales1["auth"]).json()["data"]
    assert doc["category"] == "Umum"
    client.delete(f"/api/v1/knowledge/{doc_id}", headers=sales1["auth"])


def test_reply_generate_fallback_without_groq(client, sales1):
    """Tanpa GROQ_API_KEY -> rule-based fallback tetap menghasilkan reply valid."""
    r = client.post("/api/v1/reply/generate", headers=sales1["auth"],
                    json={"message": "kak harga sertifikasi bnsp berapa?",
                          "context": {"product": "BNSP", "customer_name": "Budi"}})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["suggested_reply"].strip()
    assert isinstance(d["confidence_score"], int)
    assert isinstance(d["kb_hits"], list)
    assert isinstance(d["sources"], list)


def test_assess_fallback_components(client, sales1):
    r = client.post("/api/v1/assessment/analyze", headers=sales1["auth"],
                    json={"message": "saya mau daftar pelatihan K3 bulan ini"})
    assert r.status_code == 200
    d = r.json()["data"]
    comps = d["components"]
    for key in ("intent", "product_match", "urgency", "sentiment", "chat_history", "decision_maker"):
        assert key in comps
        assert 0 <= comps[key] <= 100
    assert 0 <= d["lead_score"] <= 100
    assert d["category"] in ("Hot Lead", "Warm Lead", "Cold Lead")

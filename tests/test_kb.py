import io

from app.kb import chunk_text, score_chunk


# ---------- unit: chunking ----------
def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text(None) == []


def test_chunk_text_short_passthrough():
    chunks = chunk_text("Paragraf pendek pertama.\n\nParagraf kedua.")
    assert len(chunks) >= 1
    assert all(c["chars"] <= 500 for c in chunks)


def test_chunk_text_long_paragraph_splits_with_overlap():
    para = "kalimat uji panjang " * 200
    chunks = chunk_text(para, size=500, overlap=80)
    assert len(chunks) > 1
    for c in chunks:
        assert c["chars"] <= 500
    assert [c["idx"] for c in chunks] == list(range(len(chunks)))


# ---------- unit: scoring ----------
def test_score_chunk_relevant_beats_irrelevant():
    query = "harga pelatihan K3 confined space"
    good = "Pelatihan K3 Confined Space dengan harga kompetitif untuk perusahaan."
    bad = "Resep masakan rendang padang asli."
    assert score_chunk(query, good) > score_chunk(query, bad)
    assert score_chunk(query, bad) == 0.0


def test_score_chunk_phrase_bonus_and_category():
    q = "jadwal sertifikasi bnsp"
    plain = score_chunk(q, "informasi umum mengenai program")
    with_cat = score_chunk(q, "informasi umum mengenai program", category="BNSP")
    assert with_cat > plain

import json
import logging

from . import db
from .security import _dev_user

log = logging.getLogger("sai")

PRODUCT_CATEGORIES = ["BNSP", "Kemnaker RI", "Reguler", "Umum"]
KB_CHUNK_SIZE = 500
KB_CHUNK_OVERLAP = 80


def chunk_text(text: str, size: int = KB_CHUNK_SIZE, overlap: int = KB_CHUNK_OVERLAP) -> list:
    text = (text or "").strip()
    if not text:
        return []
    parts, buf = [], []
    for para in text.replace("\r\n", "\n").split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            parts.append(para)
        else:
            start = 0
            while start < len(para):
                end = min(start + size, len(para))
                parts.append(para[start:end].strip())
                if end >= len(para):
                    break
                start = max(end - overlap, start + 1)
    out = []
    for p in parts:
        if out and len(out[-1]) + 1 + len(p) <= size:
            out[-1] = out[-1] + "\n" + p
        else:
            out.append(p)
    return [{"idx": i, "text": c, "chars": len(c)} for i, c in enumerate(out) if c]


def _tokens(q: str) -> set:
    stop = {"yang", "dan", "atau", "untuk", "dari", "dengan", "pada", "ini", "itu", "ada", "saya", "kami",
            "kak", "apakah", "berapa", "mohon", "info", "tentang", "the", "a", "an", "of", "to", "in"}
    return {w for w in "".join(ch.lower() if ch.isalnum() else " " for ch in (q or "")).split()
            if len(w) >= 3 and w not in stop}


def score_chunk(query: str, chunk: str, doc_name: str = "", category: str = "") -> float:
    toks = _tokens(query)
    if not toks:
        return 0.0
    blob = f"{doc_name} {category} {chunk}".lower()
    hits = sum(1 for t in toks if t in blob)
    score = hits / max(len(toks), 1)
    words = [w for w in "".join(ch.lower() if ch.isalnum() else " " for ch in query).split() if len(w) >= 3]
    for i in range(len(words) - 1):
        phrase = f"{words[i]} {words[i+1]}"
        if phrase in blob:
            score += 0.25
    if category and category.lower() in (query or "").lower():
        score += 0.15
    return round(score, 4)


def kb_rows_for_viewer(cu: dict, owner_filter: str = None) -> list:
    """Dokumen KB yang boleh dilihat cu. User: miliknya + global ('*').
    Admin all: semua. Admin spesifik: milik user itu + global."""
    if cu["role"] == "admin" and owner_filter in (None, "all"):
        return db.db_query("SELECT * FROM knowledge_base ORDER BY uploaded_at DESC LIMIT 500")
    if cu["role"] == "admin" and owner_filter:
        return db.db_query(
            "SELECT * FROM knowledge_base WHERE owner_id=? OR owner_id='*' ORDER BY uploaded_at DESC LIMIT 500",
            (owner_filter,))
    return db.db_query(
        "SELECT * FROM knowledge_base WHERE owner_id=? OR owner_id='*' ORDER BY uploaded_at DESC LIMIT 500",
        (cu["id"],))


def search_kb_chunks(query: str, category: str = None, limit: int = 5, cu: dict = None,
                     owner_filter: str = None) -> list:
    rows = kb_rows_for_viewer(cu or _dev_user(), owner_filter)
    if category and category in PRODUCT_CATEGORIES:
        rows = [r for r in rows if r.get("category") == category]
    scored = []
    for row in rows:
        chunks = row.get("chunks") or []
        if isinstance(chunks, str):
            try:
                chunks = json.loads(chunks)
            except Exception:
                chunks = []
        if not chunks and row.get("kb_text"):
            chunks = chunk_text(row["kb_text"])
        for ch in chunks:
            text = ch.get("text") if isinstance(ch, dict) else str(ch)
            if not text:
                continue
            s = score_chunk(query, text, row.get("name", ""), row.get("category", ""))
            if s <= 0:
                continue
            scored.append({
                "score": s, "text": text[:1200], "name": row.get("name", ""),
                "category": row.get("category", ""), "doc_id": row.get("id"),
                "chunk_idx": ch.get("idx") if isinstance(ch, dict) else None,
                "file_url": row.get("file_url", ""),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    out, seen = [], set()
    for item in scored:
        key = item["text"][:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def format_kb_context(chunks: list) -> str:
    if not chunks:
        return ""
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] ({c.get('category', '?')} | {c.get('name', '?')} | score={c.get('score', 0)})\n{c.get('text', '')}")
    return "\n\n".join(parts)

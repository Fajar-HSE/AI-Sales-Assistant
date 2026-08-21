import datetime
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import threading
import uuid

from . import config

log = logging.getLogger("sai")

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app.db"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
_DB_LOCK = threading.Lock()


def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def db_exec(sql, params=()):
    with _DB_LOCK:
        c = conn()
        try:
            c.execute(sql, params)
            c.commit()
        finally:
            c.close()


def db_query(sql, params=()):
    c = conn()
    try:
        rows = c.execute(sql, params).fetchall()
    finally:
        c.close()
    return [dict(r) for r in rows]


def init_db():
    db_exec("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        display_name TEXT DEFAULT '',
        fonnte_token TEXT DEFAULT '',
        fonnte_from_number TEXT DEFAULT '',
        groq_api_key TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )""")
    db_exec("""CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT NOT NULL,
        phone TEXT NOT NULL,
        name TEXT DEFAULT '',
        last_score INTEGER DEFAULT 0,
        category TEXT DEFAULT 'Cold Lead',
        badge TEXT DEFAULT '🔴',
        product TEXT DEFAULT 'Umum',
        last_message TEXT DEFAULT '',
        unread INTEGER DEFAULT 0,
        created_at TEXT,
        last_updated TEXT,
        UNIQUE(owner_id, phone)
    )""")
    db_exec("""CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT NOT NULL,
        phone TEXT NOT NULL,
        text TEXT DEFAULT '',
        direction TEXT DEFAULT 'in',
        timestamp TEXT,
        lead_score INTEGER,
        category TEXT,
        intent_label TEXT,
        sender_name TEXT
    )""")
    db_exec("""CREATE TABLE IF NOT EXISTS knowledge_base (
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        category TEXT DEFAULT 'Umum',
        name TEXT DEFAULT '',
        filename TEXT DEFAULT '',
        file_url TEXT DEFAULT '',
        kb_text TEXT DEFAULT '',
        chunks TEXT DEFAULT '[]',
        chunk_count INTEGER DEFAULT 0,
        uploaded_at TEXT
    )""")
    db_exec("""CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        name TEXT DEFAULT '',
        category TEXT DEFAULT 'Umum',
        description TEXT DEFAULT '',
        price_range TEXT DEFAULT '',
        duration TEXT DEFAULT '',
        kb_text TEXT DEFAULT '',
        created_at TEXT
    )""")
    db_exec("CREATE INDEX IF NOT EXISTS idx_cust_owner ON customers(owner_id)")
    db_exec("CREATE INDEX IF NOT EXISTS idx_chats_owner_phone ON chats(owner_id, phone)")
    db_exec("CREATE INDEX IF NOT EXISTS idx_kb_owner ON knowledge_base(owner_id)")


# ---------- PASSWORD HASHING ----------
def hash_password(pw: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100000).hex()
    return f"pbkdf2_sha256$100000${salt}${dk}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it)).hex()
        return hmac.compare_digest(calc, dk)
    except Exception:
        return False


# ---------- USER HELPERS ----------
def _row_to_user(r: dict) -> dict:
    return {
        "id": r["id"], "username": r["username"], "role": r["role"],
        "display_name": r.get("display_name") or r["username"],
        "fonnte_token": r.get("fonnte_token") or "",
        "fonnte_from_number": r.get("fonnte_from_number") or "",
        "groq_api_key": r.get("groq_api_key") or "",
        "is_active": bool(r.get("is_active", 1)),
        "created_at": r.get("created_at"),
    }


def get_user_by_id(uid: str):
    rows = db_query("SELECT * FROM users WHERE id=?", (uid,))
    return _row_to_user(rows[0]) if rows else None


def get_user_by_username(uname: str):
    rows = db_query("SELECT * FROM users WHERE username=?", (uname,))
    return _row_to_user(rows[0]) if rows else None


def list_users():
    rows = db_query("SELECT * FROM users ORDER BY created_at ASC")
    return [_row_to_user(r) for r in rows]


def create_user(uname, pw, role="user", display_name="", fonnte_token="", fonnte_from="", groq_key=""):
    uid = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db_exec(
        "INSERT INTO users (id,username,password_hash,role,display_name,fonnte_token,fonnte_from_number,groq_api_key,is_active,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,1,?,?)",
        (uid, uname, hash_password(pw), role, display_name or uname, fonnte_token, fonnte_from, groq_key, now, now))
    return get_user_by_id(uid)


def update_user(uid, **fields):
    allowed = {"role", "display_name", "username", "fonnte_token", "fonnte_from_number", "groq_api_key", "is_active"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return get_user_by_id(uid)
    sets.append("updated_at=?")
    params.append(datetime.datetime.now(datetime.timezone.utc).isoformat())
    params.append(uid)
    db_exec(f"UPDATE users SET {','.join(sets)} WHERE id=?", tuple(params))
    return get_user_by_id(uid)


def delete_user(uid):
    with _DB_LOCK:
        c = conn()
        try:
            c.execute("DELETE FROM users WHERE id=?", (uid,))
            c.execute("DELETE FROM customers WHERE owner_id=?", (uid,))
            c.execute("DELETE FROM chats WHERE owner_id=?", (uid,))
            c.execute("DELETE FROM knowledge_base WHERE owner_id=?", (uid,))
            c.execute("DELETE FROM products WHERE owner_id=?", (uid,))
            c.commit()
        finally:
            c.close()


def set_password(uid, pw):
    db_exec("UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
            (hash_password(pw), datetime.datetime.now(datetime.timezone.utc).isoformat(), uid))


def password_hash_for(username):
    rows = db_query("SELECT password_hash FROM users WHERE username=?", (username,))
    return rows[0]["password_hash"] if rows else ""


def seed_admin():
    """Seed admin awal HANYA jika ADMIN_PASSWORD diset di env.

    Tidak ada lagi default password lemah ('admin123'): jika env kosong,
    admin tidak dibuat dan server mencatat instruksi konfigurasi.
    """
    rows = db_query("SELECT id FROM users LIMIT 1")
    if rows:
        return
    uname = config.ADMIN_USER or "admin"
    pw = config.ADMIN_PASSWORD
    if not pw:
        log.error(
            "[Seed] Tabel users kosong dan ADMIN_PASSWORD tidak diset. "
            "Set ADMIN_PASSWORD (min 8 karakter) di .env lalu restart untuk membuat admin '%s'.",
            uname,
        )
        return
    if len(pw) < 8:
        log.error("[Seed] ADMIN_PASSWORD harus minimal 8 karakter. Admin tidak dibuat.")
        return
    create_user(uname, pw, "admin", display_name=uname)
    log.warning("[Seed] Admin dibuat: %s (password dari env ADMIN_PASSWORD)", uname)


# ---------- CUSTOMER / CHAT STORE ----------
def ensure_customer(owner_id, phone, name=None, analysis=None):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    existing = db_query("SELECT * FROM customers WHERE owner_id=? AND phone=?", (owner_id, phone))
    if existing:
        if name and existing[0]["name"] in (None, "", phone):
            db_exec("UPDATE customers SET name=?, last_updated=? WHERE id=?", (name, now, existing[0]["id"]))
        if analysis:
            db_exec("UPDATE customers SET last_score=?, category=?, badge=?, product=?, last_updated=? WHERE id=?",
                    (analysis.get("lead_score", 0), analysis.get("category", "Cold Lead"), analysis.get("badge", "🔴"),
                     analysis.get("product", "Umum"), now, existing[0]["id"]))
        return db_query("SELECT * FROM customers WHERE owner_id=? AND phone=?", (owner_id, phone))[0]
    db_exec("INSERT INTO customers (owner_id,phone,name,last_score,category,badge,product,created_at,last_updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (owner_id, phone, name or phone,
             (analysis or {}).get("lead_score", 0), (analysis or {}).get("category", "Cold Lead"),
             (analysis or {}).get("badge", "🔴"), (analysis or {}).get("product", "Umum"), now, now))
    return db_query("SELECT * FROM customers WHERE owner_id=? AND phone=?", (owner_id, phone))[0]


def append_chat(owner_id, phone, text, direction, analysis=None, name=None):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db_exec("INSERT INTO chats (owner_id,phone,text,direction,timestamp,lead_score,category,intent_label,sender_name) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (owner_id, phone, text, direction, now,
             (analysis or {}).get("lead_score"), (analysis or {}).get("category"),
             (analysis or {}).get("intent_label"), name))
    if direction == "in":
        db_exec("UPDATE customers SET unread=unread+1, last_message=?, last_updated=? WHERE owner_id=? AND phone=?",
                (text[:200], now, owner_id, phone))
    else:
        db_exec("UPDATE customers SET unread=0, last_message=?, last_updated=? WHERE owner_id=? AND phone=?",
                (text[:200], now, owner_id, phone))


def get_customer_dict(row, msgs=None):
    return {
        "phone": row["phone"], "name": row.get("name") or row["phone"],
        "owner_id": row.get("owner_id"),
        "score": row.get("last_score", 0) or 0, "category": row.get("category") or "Cold Lead",
        "badge": row.get("badge") or "🔴", "product": row.get("product") or "Umum",
        "last": row.get("last_message") or "", "unread": row.get("unread", 0) or 0,
        "created": row.get("created_at"), "stage": "Awareness", "msgs": msgs or [],
    }

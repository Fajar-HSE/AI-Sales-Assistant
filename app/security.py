import datetime
import hmac
import logging
import time

import jwt as pyjwt
from fastapi import Header, HTTPException, Request

from . import config, db

log = logging.getLogger("sai")


def create_token(user: dict) -> str:
    if not (pyjwt and config.JWT_SECRET_KEY):
        raise HTTPException(403, "Login disabled: set JWT_SECRET_KEY")
    payload = {
        "sub": user["id"], "role": user["role"], "username": user["username"],
        "name": user["display_name"],
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=config.JWT_EXPIRATION),
    }
    return pyjwt.encode(payload, config.JWT_SECRET_KEY, algorithm="HS256")


def _dev_user():
    return {"id": "dev", "role": "admin", "username": "dev", "display_name": "Dev", "is_active": True,
            "fonnte_token": config.FONNTE_TOKEN, "fonnte_from_number": config.FONNTE_FROM,
            "groq_api_key": config.GROQ_API_KEY,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}


async def get_current_user(request: Request, authorization: str = Header(default="")) -> dict:
    """Dependency auth untuk semua /api/v1/*. Tanpa konfigurasi auth => 503."""
    if not config.AUTH_ENABLED:
        if config.ALLOW_DEV_MODE:
            return _dev_user()
        raise HTTPException(503, "Auth belum dikonfigurasi")
    scheme, _, token = authorization.partition(" ")
    token = token.strip() if scheme.lower() == "bearer" else authorization.strip()
    if not token:
        raise HTTPException(401, "Unauthorized")
    if config.API_TOKEN and hmac.compare_digest(token, config.API_TOKEN):
        return _dev_user()
    if pyjwt and config.JWT_SECRET_KEY:
        try:
            payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        except Exception:
            log.info("[Auth] Token decode gagal dari %s", request.client.host if request.client else "?")
            raise HTTPException(401, "Token tidak valid")
        u = db.get_user_by_id(payload.get("sub"))
        if not u:
            raise HTTPException(401, "User tidak ditemukan")
        if not u["is_active"]:
            raise HTTPException(403, "User non-aktif")
        return u
    raise HTTPException(401, "Unauthorized")


def require_admin(cu: dict):
    if cu["role"] != "admin":
        raise HTTPException(403, "Hanya admin")


def scope_owner(cu: dict, req_owner: str = None):
    """Admin: req_owner='all'/kosong => None (semua owner); req_owner=<uid> => owner spesifik.
    User biasa: selalu dirinya sendiri."""
    if cu["role"] != "admin":
        return cu["id"]
    if req_owner in (None, "", "all", "me"):
        return None
    return req_owner


def public_user(u: dict) -> dict:
    return {
        "id": u["id"], "username": u["username"], "role": u["role"],
        "display_name": u["display_name"], "is_active": u["is_active"],
        "created_at": u.get("created_at"),
        "fonnte_from_number": u.get("fonnte_from_number", ""),
        "has_fonnte_token": bool(u.get("fonnte_token")),
        "has_groq_key": bool(u.get("groq_api_key")),
    }


# ---------- RATE LIMITING (in-memory) ----------
_RATE_HITS = {}


def rate_limited(key: str, limit: int = None, window: int = None) -> bool:
    """Return True jika request harus ditolak (limit tercapai)."""
    limit = limit if limit is not None else config.RATE_MAX
    window = window if window is not None else config.RATE_WINDOW
    now = time.time()
    hits = [t for t in _RATE_HITS.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _RATE_HITS[key] = hits
        return False
    hits.append(now)
    _RATE_HITS[key] = hits
    return True

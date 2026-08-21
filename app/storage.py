import logging
import os
import uuid

from fastapi import UploadFile

from . import config

log = logging.getLogger("sai")

HAS_SUPABASE = bool(config.SUPABASE_URL and (config.SUPABASE_KEY or config.SUPABASE_SERVICE_KEY))

supabase_admin = None
if HAS_SUPABASE:
    try:
        from supabase import create_client
        supabase_admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY or config.SUPABASE_KEY)
        log.warning("[Supabase] Connected to %s", config.SUPABASE_URL)
    except Exception as e:
        supabase_admin = None
        log.warning("[Supabase] Not available (SQLite digunakan sebagai store utama): %s", e)


async def upload_to_storage(file: UploadFile) -> dict:
    """Upload file produk ke Supabase Storage (jika ada), else mock."""
    if not HAS_SUPABASE or supabase_admin is None:
        content = await file.read()
        return {"status": "mock", "filename": file.filename, "size": len(content)}
    try:
        content = await file.read()
        ext = os.path.splitext(file.filename or "")[1]
        fname = f"{uuid.uuid4().hex}{ext}"
        res = supabase_admin.storage.from_("products").upload(fname, content)
        if res.status_code == 200:
            public_url = supabase_admin.storage.from_("products").get_public_url(fname)
            return {"status": "uploaded", "filename": fname, "public_url": public_url}
        log.warning("[Storage] Upload gagal status=%s", getattr(res, "status_code", "?"))
        return {"status": "error", "error": "storage_upload_failed"}
    except Exception:
        log.exception("[Storage] Upload error")
        return {"status": "error", "error": "storage_error"}

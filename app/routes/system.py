import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .. import config, db
from ..ws import manager

log = logging.getLogger("sai")
router = APIRouter()


@router.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse(config.FRONTEND_FILE)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.get("/health")
async def health():
    users = db.db_query("SELECT COUNT(*) c FROM users")
    all_users = db.list_users()
    return {"status": "ok", "version": config.APP_VERSION, "multi_user": True,
            "groq_ready": bool(config.GROQ_API_KEY or any(u["groq_api_key"] for u in all_users)),
            "groq_model": config.GROQ_MODEL,
            "fonnte_ready": bool(config.FONNTE_TOKEN or any(u["fonnte_token"] for u in all_users)),
            "db": "sqlite", "user_count": users[0]["c"] if users else 0,
            "auth_enabled": config.AUTH_ENABLED,
            "webhook_secured": bool(config.WEBHOOK_SECRET),
            "rate_max": config.RATE_MAX, "rate_window": config.RATE_WINDOW}

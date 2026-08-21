import datetime
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import config, db
from ..fonnte import fonnte_send, fonnte_token_for
from ..kb import PRODUCT_CATEGORIES, format_kb_context, search_kb_chunks
from ..llm import groq_for
from ..schemas import AssessRequest, MessageSend, ReplyRequest
from ..security import _dev_user, get_current_user, rate_limited, scope_owner
from ..ws import manager

log = logging.getLogger("sai")
router = APIRouter(tags=["chat"])


# ---------- WHATSAPP WEBHOOK ----------
def _webhook_owner(req: Request) -> dict:
    uid = req.query_params.get("uid")
    if uid:
        u = db.get_user_by_id(uid)
        if u and u["is_active"]:
            return u
    rows = db.db_query("SELECT * FROM users WHERE is_active=1 LIMIT 1")
    return db._row_to_user(rows[0]) if rows else _dev_user()


def _webhook_ok(request: Request) -> bool:
    if not config.WEBHOOK_SECRET:
        # Secure by default: webhook tanpa token ditolak kecuali dev mode eksplisit.
        return bool(config.ALLOW_DEV_MODE)
    header = request.headers.get("x-webhook-token", "")
    query = request.query_params.get("token", "")
    try:
        if header and hmac.compare_digest(header, config.WEBHOOK_SECRET):
            return True
        if query and hmac.compare_digest(query, config.WEBHOOK_SECRET):
            return True
    except Exception:
        return False
    return False


def process_incoming(payload: dict, owner: dict):
    sender = payload.get("sender") or payload.get("pengirim") or payload.get("from")
    text = payload.get("message") or payload.get("pesan") or payload.get("text")
    name = payload.get("name") or payload.get("pushname") or sender
    if not sender or not text:
        return None, None, None
    g = groq_for(owner)
    analysis = g.analyze(str(text))
    cust_row = db.ensure_customer(owner["id"], str(sender), name, analysis)
    db.append_chat(owner["id"], str(sender), str(text), "in", analysis, name)
    cust = db.get_customer_dict(cust_row)
    msg = {"from": str(sender), "text": str(text),
           "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    log.info("[incoming] owner=%s %s (%s) -> %s (score=%s)",
             owner["id"], sender, name, str(text)[:60], analysis["lead_score"])
    return cust, msg, analysis


@router.post("/webhook/fonnte")
async def webhook_fonnte(req: Request):
    if not _webhook_ok(req):
        raise HTTPException(401, "Invalid webhook token")
    try:
        payload = await req.json()
        if not isinstance(payload, dict):
            raise ValueError("bukan objek JSON")
    except Exception:
        log.info("[Webhook] Payload tidak valid dari %s", req.client.host if req.client else "?")
        raise HTTPException(400, "Payload JSON tidak valid")
    client_ip = req.client.host if req.client else "?"
    if not rate_limited(f"wh:{client_ip}:{payload.get('sender', '')}", limit=120):
        raise HTTPException(429, "Too many webhook requests")
    if "stateid" in payload or ("device" in payload and "message" not in payload and "sender" not in payload):
        return {"status": "received", "type": "device_status"}
    owner = _webhook_owner(req)
    cust, msg, analysis = process_incoming(payload, owner)
    if cust is None:
        return {"status": "received", "type": "skip"}
    await manager.broadcast({"type": "chat_incoming", "customer": cust, "message": msg,
                             "analysis": analysis, "owner_id": owner["id"]})
    return {"status": "received", "type": "message"}


@router.post("/webhook/fonte")
async def webhook_fonte(req: Request):
    return await webhook_fonnte(req)


# ---------- ANALYTICS / REPLY ----------
@router.post("/api/v1/assessment/analyze")
async def assess(body: AssessRequest, cu: dict = Depends(get_current_user)):
    g = groq_for(cu)
    analysis = g.analyze(body.message, body.chat_history)
    return {"status": "success", "data": analysis}


@router.post("/api/v1/reply/generate")
async def reply_generate(body: ReplyRequest, cu: dict = Depends(get_current_user)):
    kb = body.knowledge_chunks
    product = (body.context or {}).get("product", "Umum")
    message = body.message
    hits = []
    if not kb:
        cat_match = None
        for cat in PRODUCT_CATEGORIES:
            if cat.lower() in (product or "").lower() or cat.lower() in (message or "").lower():
                cat_match = cat
                break
        owner_filter = scope_owner(cu, body.owner)
        hits = search_kb_chunks(message or product, category=cat_match, limit=5,
                                cu=cu, owner_filter=owner_filter)
        if not hits and cat_match:
            hits = search_kb_chunks(message or product, category=None, limit=5,
                                    cu=cu, owner_filter=owner_filter)
        kb = format_kb_context(hits)
    g = groq_for(cu)
    reply = g.generate_reply(message, body.context or {}, kb)
    if isinstance(reply, dict) and "suggested_reply" in reply:
        reply["kb_hits"] = [{"name": h.get("name"), "category": h.get("category"),
                             "score": h.get("score"), "chunk_idx": h.get("chunk_idx")} for h in hits]
        extra = [{"type": "kb",
                  "reference": f"{h.get('category', '')}/{h.get('name', '')}#{h.get('chunk_idx')}"}
                 for h in hits[:3]]
        reply["sources"] = (reply.get("sources") or []) + extra
        reply["confidence"] = reply.get("confidence_score", 0)
    else:
        reply = {"suggested_reply": "(fallback error)", "confidence_score": 20,
                 "sources": [], "fallback": "error", "kb_hits": []}
    return {"status": "success", "data": reply}


# ---------- MESSAGES ----------
@router.post("/api/v1/messages/send")
async def send_message(body: MessageSend, cu: dict = Depends(get_current_user)):
    owner_id = scope_owner(cu, body.owner)
    if owner_id is None:
        owner_id = cu["id"]
    owner = cu if owner_id == cu["id"] else (db.get_user_by_id(owner_id) or cu)
    token = fonnte_token_for(owner)
    client_ip = cu["id"]
    if not rate_limited(f"send:{client_ip}:{body.to}"):
        raise HTTPException(429, "Too many messages, please slow down")
    res = await fonnte_send(body.to, body.text, token)
    db.append_chat(owner["id"], body.to, body.text, "out")
    return {"status": "success", "sent": res.get("status_code") == 200,
            "fonnte": res, "owner_id": owner["id"]}

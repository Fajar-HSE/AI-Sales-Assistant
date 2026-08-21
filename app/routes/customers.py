import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import db
from ..security import get_current_user, scope_owner

log = logging.getLogger("sai")
router = APIRouter(prefix="/api/v1", tags=["customers"])


def _fmt_ts(ts):
    if not ts:
        return ""
    try:
        if isinstance(ts, str):
            parsed = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            parsed = ts
        if parsed.tzinfo is None:
            return parsed.strftime("%H:%M")
        return parsed.astimezone().strftime("%H:%M")
    except Exception:
        s = str(ts)
        return s[11:16] if len(s) >= 16 else s


@router.get("/customers/{phone}/messages")
async def customer_messages(phone: str, req: Request, cu: dict = Depends(get_current_user)):
    owner_id = scope_owner(cu, req.query_params.get("owner"))
    if owner_id is None:
        rows = db.db_query("SELECT * FROM chats WHERE phone=? ORDER BY timestamp ASC LIMIT 200", (phone,))
    else:
        rows = db.db_query("SELECT * FROM chats WHERE owner_id=? AND phone=? ORDER BY timestamp ASC LIMIT 200",
                           (owner_id, phone))
    msgs = [{"dir": (r.get("direction") or "in"), "t": _fmt_ts(r.get("timestamp")),
             "d": (r.get("text") or ""), "ts": r.get("timestamp")} for r in rows]
    if owner_id is not None:
        db.db_exec("UPDATE customers SET unread=0 WHERE owner_id=? AND phone=?", (owner_id, phone))
    else:
        db.db_exec("UPDATE customers SET unread=0 WHERE phone=?", (phone,))
    return {"status": "success", "data": msgs, "count": len(msgs)}


@router.get("/customers")
async def list_customers(req: Request, cu: dict = Depends(get_current_user)):
    owner_id = scope_owner(cu, req.query_params.get("owner"))
    if owner_id is None:
        rows = db.db_query("SELECT * FROM customers ORDER BY last_updated DESC LIMIT 500")
    else:
        rows = db.db_query("SELECT * FROM customers WHERE owner_id=? ORDER BY last_updated DESC LIMIT 500",
                           (owner_id,))
    return [db.get_customer_dict(r) for r in rows]


@router.get("/stats")
async def get_stats(req: Request, cu: dict = Depends(get_current_user)):
    owner_id = scope_owner(cu, req.query_params.get("owner"))
    now = datetime.datetime.now(datetime.timezone.utc)
    hot = warm = cold = 0
    chat_in = 0
    product_counts = {}
    activity = {}
    if owner_id is None:
        cust_rows = db.db_query("SELECT category,product FROM customers")
        chat_rows = db.db_query("SELECT timestamp FROM chats WHERE direction='in'")
    else:
        cust_rows = db.db_query("SELECT category,product FROM customers WHERE owner_id=?", (owner_id,))
        chat_rows = db.db_query("SELECT timestamp FROM chats WHERE owner_id=? AND direction='in'", (owner_id,))
    for r in cust_rows:
        cat = r.get("category") or "Cold Lead"
        if "Hot" in cat:
            hot += 1
        elif "Warm" in cat:
            warm += 1
        else:
            cold += 1
        prod = r.get("product") or "Umum"
        product_counts[prod] = product_counts.get(prod, 0) + 1
    for r in chat_rows:
        ts = r.get("timestamp")
        if ts:
            day = ts[:10]
            activity[day] = activity.get(day, 0) + 1
            chat_in += 1
    total = hot + warm + cold
    days = []
    for i in range(6, -1, -1):
        ddate = (now - datetime.timedelta(days=i)).date()
        label = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"][ddate.weekday()]
        days.append({"label": label, "date": ddate.isoformat(), "value": activity.get(ddate.isoformat(), 0)})
    top_products = [{"name": k, "count": v, "sub": ""} for k, v in
                    sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:5]]
    return {"status": "success", "data": {
        "owner_id": owner_id, "scope": "all" if owner_id is None else owner_id,
        "chat_count": chat_in,
        "hot": hot, "warm": warm, "cold": cold, "total": total,
        "distribution": {
            "hot": round(hot / total * 100) if total else 0,
            "warm": round(warm / total * 100) if total else 0,
            "cold": round(cold / total * 100) if total else 0,
        },
        "avg_response_sec": None,
        "activity": days,
        "top_products": top_products,
        "response_trend": [],
        "generated_at": now.isoformat(),
    }}

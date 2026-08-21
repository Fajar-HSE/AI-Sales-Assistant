import logging

import httpx

from . import config

log = logging.getLogger("sai")


def fonnte_token_for(owner: dict) -> str:
    return (owner or {}).get("fonnte_token") or config.FONNTE_TOKEN


async def fonnte_send(target: str, text: str, token: str = None) -> dict:
    """Kirim pesan WA via Fonnte API. Token diambil dari user owner (fallback env)."""
    tk = token or config.FONNTE_TOKEN
    if not tk:
        return {"status_code": 0, "error": "FONNTE_TOKEN not set"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://api.fonnte.com/send",
                              data={"target": target, "message": text, "countryCode": "62"},
                              headers={"Authorization": tk})
        return {"status_code": r.status_code, "response": r.text}


async def fonnte_device_status(tk: str) -> dict:
    """Cek reachability device token ke Fonnte. Return dict connected/detail."""
    if not tk:
        return {"connected": False, "detail": "no_token"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post("https://api.fonnte.com/get-devices", headers={"Authorization": tk})
    except Exception:
        return {"connected": False, "detail": "network_error"}
    if r.status_code != 200:
        return {"connected": False, "detail": f"http_{r.status_code}"}
    try:
        j = r.json()
    except Exception:
        j = {}
    reason = str(j.get("reason", "")).lower()
    if j.get("status") is False and ("token invalid" in reason or "unauthoriz" in reason):
        return {"connected": False, "detail": "token_invalid"}
    return {"connected": True, "detail": str(r.status_code)}

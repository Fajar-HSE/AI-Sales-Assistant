import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import config, db
from ..fonnte import fonnte_device_status, fonnte_token_for
from ..schemas import LoginRequest, MeUpdate
from ..security import create_token, get_current_user, public_user, rate_limited

log = logging.getLogger("sai")
router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/auth/login")
async def auth_login(req: Request, body: LoginRequest):
    if not (config.JWT_SECRET_KEY):
        raise HTTPException(403, "Login disabled: set JWT_SECRET_KEY")
    client_ip = req.client.host if req.client else "?"
    u = body.username.strip()
    if not rate_limited(f"login:{client_ip}:{u.lower()}", limit=10, window=300):
        raise HTTPException(429, "Terlalu banyak percobaan login. Tunggu beberapa saat.")
    user = db.get_user_by_username(u)
    stored = db.password_hash_for(u)
    if not user or not stored or not db.verify_password(body.password, stored):
        # Pesan identik untuk user tak dikenal & password salah (anti user enumeration)
        raise HTTPException(401, "Username atau password salah")
    if not user["is_active"]:
        raise HTTPException(403, "User non-aktif")
    token = create_token(user)
    return {"status": "success", "token": token, "expires_in": config.JWT_EXPIRATION,
            "user": {"id": user["id"], "username": user["username"], "role": user["role"],
                     "display_name": user["display_name"]}}


@router.get("/me")
async def me(cu: dict = Depends(get_current_user)):
    return {"status": "success", "data": public_user(cu)}


@router.put("/me")
async def update_me(body: MeUpdate, cu: dict = Depends(get_current_user)):
    fields = {}
    if body.display_name is not None:
        fields["display_name"] = body.display_name.strip()[:80]
    if body.username is not None:
        nu = body.username.strip()
        if nu != cu["username"] and db.get_user_by_username(nu):
            raise HTTPException(409, "Username sudah dipakai")
        fields["username"] = nu
    if body.fonnte_token is not None:
        fields["fonnte_token"] = body.fonnte_token
    if body.fonnte_from_number is not None:
        fields["fonnte_from_number"] = body.fonnte_from_number
    if body.new_password:
        if not body.current_password or not db.verify_password(
                body.current_password, db.password_hash_for(cu["username"])):
            raise HTTPException(400, "Password saat ini salah")
        db.set_password(cu["id"], body.new_password)
    if fields:
        db.update_user(cu["id"], **fields)
    updated = db.get_user_by_id(cu["id"])
    return {"status": "success", "data": public_user(updated)}


@router.get("/fonnte/status")
async def fonnte_status(cu: dict = Depends(get_current_user)):
    """Cek koneksi gateway WA (Fonnte) milik user yang login."""
    result = await fonnte_device_status(fonnte_token_for(cu))
    return {"status": "success", **result}

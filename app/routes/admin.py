import logging

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..schemas import UserCreate, UserUpdate
from ..security import get_current_user, public_user, require_admin

log = logging.getLogger("sai")
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users")
async def admin_list_users(cu: dict = Depends(get_current_user)):
    require_admin(cu)
    return {"status": "success", "data": [public_user(u) for u in db.list_users()]}


@router.post("/users")
async def admin_create_user(body: UserCreate, cu: dict = Depends(get_current_user)):
    require_admin(cu)
    if db.get_user_by_username(body.username):
        raise HTTPException(409, "Username sudah dipakai")
    u = db.create_user(body.username, body.password, body.role,
                       display_name=body.display_name or body.username,
                       fonnte_token=body.fonnte_token,
                       fonnte_from=body.fonnte_from_number)
    return {"status": "success", "data": public_user(u)}


@router.put("/users/{uid}")
async def admin_update_user(uid: str, body: UserUpdate, cu: dict = Depends(get_current_user)):
    require_admin(cu)
    if uid == cu["id"] and body.role == "user":
        raise HTTPException(400, "Tidak bisa menurunkan role sendiri")
    fields = {}
    if body.role is not None:
        fields["role"] = body.role
    if body.display_name is not None:
        fields["display_name"] = body.display_name.strip()[:80]
    if body.username is not None:
        nu = body.username.strip()
        cur = db.get_user_by_id(uid) or {}
        if nu != cur.get("username") and db.get_user_by_username(nu):
            raise HTTPException(409, "Username sudah dipakai")
        fields["username"] = nu
    if body.fonnte_token is not None:
        fields["fonnte_token"] = body.fonnte_token
    if body.fonnte_from_number is not None:
        fields["fonnte_from_number"] = body.fonnte_from_number
    if body.is_active is not None:
        fields["is_active"] = 1 if body.is_active else 0
    if body.new_password:
        db.set_password(uid, body.new_password)
    if fields:
        db.update_user(uid, **fields)
    u = db.get_user_by_id(uid)
    if not u:
        raise HTTPException(404, "User tidak ditemukan")
    return {"status": "success", "data": public_user(u)}


@router.delete("/users/{uid}")
async def admin_delete_user(uid: str, cu: dict = Depends(get_current_user)):
    require_admin(cu)
    if uid == cu["id"]:
        raise HTTPException(400, "Tidak bisa menghapus diri sendiri")
    if not db.get_user_by_id(uid):
        raise HTTPException(404, "User tidak ditemukan")
    db.delete_user(uid)
    return {"status": "success", "deleted": uid}

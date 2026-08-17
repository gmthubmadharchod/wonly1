from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from bson import ObjectId
from ..db import users, files_col, folders
from ..security import require_admin
from ..config import settings
from ..utils import now

router = APIRouter(prefix="/api/admin")

def oid(value):
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(400, "Invalid user id")

class StorageIn(BaseModel):
    gb: float = Field(ge=0, le=10000)

class PlanIn(BaseModel):
    plan: str

class UserStateIn(BaseModel):
    banned: bool

class ExpiryIn(BaseModel):
    days: int = Field(ge=0, le=3650)

class SettingsIn(BaseModel):
    free_storage_gb: float = Field(ge=0, le=10000)
    premium_storage_gb: float = Field(ge=0, le=10000)
    free_expiry_days: int = Field(ge=0, le=3650)
    max_user_quota_gb: float = Field(ge=0, le=10000)
    admin_email: str = Field(min_length=3, max_length=320)
    admin_password: str = Field(min_length=8, max_length=200)

@router.get("/stats")
async def stats(request: Request):
    require_admin(request)
    storage_used = 0
    async for x in users.find({}, {"used_storage": 1}):
        storage_used += int(x.get("used_storage", 0))
    return {
        "users": await users.count_documents({}),
        "premium": await users.count_documents({"plan": "premium"}),
        "admins": await users.count_documents({"role": "admin"}),
        "banned": await users.count_documents({"banned": True}),
        "files": await files_col.count_documents({"deleted": False}),
        "folders": await folders.count_documents({"deleted": False}),
        "storage_used": storage_used,
        "admin_email": settings.admin_email,
    }

@router.get("/users")
async def user_list(request: Request, q: str = ""):
    require_admin(request)
    query = {}
    if q.strip():
        term = q.strip()
        query = {"$or": [
            {"email": {"$regex": term, "$options": "i"}},
            {"name": {"$regex": term, "$options": "i"}},
        ]}
    out = []
    async for u in users.find(query, {"password_hash": 0}).sort("created_at", -1):
        uid = str(u["_id"])
        file_count = await files_col.count_documents({"owner_id": uid, "deleted": False})
        out.append({
            "id": uid,
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "role": u.get("role", "user"),
            "plan": u.get("plan", "free"),
            "banned": bool(u.get("banned", False)),
            "used_storage": int(u.get("used_storage", 0)),
            "storage_limit": int(u.get("storage_limit", 0)),
            "file_count": file_count,
            "created_at": u.get("created_at").isoformat() if u.get("created_at") else None,
            "telegram_user_id": u.get("telegram_user_id"),
        })
    return {"users": out}

@router.get("/users/{user_id}")
async def user_detail(request: Request, user_id: str):
    require_admin(request)
    u = await users.find_one({"_id": oid(user_id)}, {"password_hash": 0})
    if not u:
        raise HTTPException(404, "User not found")
    uid = str(u["_id"])
    files = []
    async for f in files_col.find({"owner_id": uid, "deleted": False}).sort("created_at", -1).limit(200):
        files.append({
            "id": str(f["_id"]),
            "name": f.get("name"),
            "size": f.get("size", 0),
            "mime": f.get("mime"),
            "expires_at": f.get("expires_at").isoformat() if f.get("expires_at") else None,
            "created_at": f.get("created_at").isoformat() if f.get("created_at") else None,
        })
    return {
        "user": {
            "id": uid,
            "name": u.get("name"),
            "email": u.get("email"),
            "role": u.get("role", "user"),
            "plan": u.get("plan", "free"),
            "banned": bool(u.get("banned", False)),
            "used_storage": int(u.get("used_storage", 0)),
            "storage_limit": int(u.get("storage_limit", 0)),
            "telegram_user_id": u.get("telegram_user_id"),
            "created_at": u.get("created_at").isoformat() if u.get("created_at") else None,
        },
        "files": files
    }

@router.post("/users/{user_id}/plan")
async def set_plan(request: Request, user_id: str, data: PlanIn):
    require_admin(request)
    if data.plan not in ("free", "premium"):
        raise HTTPException(400, "Plan must be free or premium")
    limit = settings.premium_storage if data.plan == "premium" else settings.free_storage
    await users.update_one({"_id": oid(user_id)}, {"$set": {"plan": data.plan, "storage_limit": limit}})
    return {"ok": True}

@router.post("/users/{user_id}/storage")
async def set_storage(request: Request, user_id: str, data: StorageIn):
    require_admin(request)
    bytes_value = int(data.gb * 1024**3)
    if bytes_value > settings.max_admin_storage:
        raise HTTPException(400, "Storage exceeds MAX_ADMIN_STORAGE")
    result = await users.update_one({"_id": oid(user_id)}, {"$set": {"storage_limit": bytes_value}})
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True, "storage_limit": bytes_value}

@router.post("/users/{user_id}/state")
async def set_state(request: Request, user_id: str, data: UserStateIn):
    require_admin(request)
    result = await users.update_one({"_id": oid(user_id)}, {"$set": {"banned": data.banned}})
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}

@router.post("/users/{user_id}/expiry")
async def set_expiry(request: Request, user_id: str, data: ExpiryIn):
    require_admin(request)
    from datetime import timedelta
    user = await users.find_one({"_id": oid(user_id)})
    if not user:
        raise HTTPException(404, "User not found")
    expires = None if data.days == 0 else now() + timedelta(days=data.days)
    await users.update_one({"_id": oid(user_id)}, {"$set": {"account_expires_at": expires}})
    return {"ok": True, "account_expires_at": expires.isoformat() if expires else None}

@router.get("/settings")
async def get_settings(request: Request):
    require_admin(request)
    cfg = await users.find_one({"_settings": True})
    return {
        "free_storage_gb": round((cfg or {}).get("free_storage", settings.free_storage) / 1024**3, 2),
        "premium_storage_gb": round((cfg or {}).get("premium_storage", settings.premium_storage) / 1024**3, 2),
        "free_expiry_days": (cfg or {}).get("free_expiry_days", settings.free_expiry_days),
        "max_user_quota_gb": round((cfg or {}).get("max_user_quota", settings.max_admin_storage) / 1024**3, 2),
        "admin_email": settings.admin_email
    }

@router.post("/settings")
async def update_settings(request: Request, data: SettingsIn):
    require_admin(request)
    from ..security import hash_password
    from bson import ObjectId
    from datetime import datetime, timezone
    free_b = int(data.free_storage_gb * 1024**3)
    premium_b = int(data.premium_storage_gb * 1024**3)
    max_b = int(data.max_user_quota_gb * 1024**3)
    if premium_b > max_b:
        raise HTTPException(400, "Premium storage cannot exceed max user quota")
    if not data.admin_email or "@" not in data.admin_email:
        raise HTTPException(400, "Invalid admin email")

    await users.update_one(
        {"_settings": True},
        {"$set": {
            "_settings": True,
            "free_storage": free_b,
            "premium_storage": premium_b,
            "free_expiry_days": data.free_expiry_days,
            "max_user_quota": max_b,
            "admin_email": data.admin_email.strip().lower(),
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )

    # Update the owner/admin account credentials.
    owner = await users.find_one({"role": "admin"})
    if not owner:
        raise HTTPException(404, "Owner account not found")
    await users.update_one(
        {"_id": owner["_id"]},
        {"$set": {
            "email": data.admin_email.strip().lower(),
            "password_hash": hash_password(data.admin_password)
        }}
    )
    return {"ok": True, "message": "Settings updated. Restart recommended for environment-level defaults; database settings are saved immediately."}

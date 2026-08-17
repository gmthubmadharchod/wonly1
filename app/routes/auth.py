from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from ..db import users
from ..security import hash_password, verify_password, create_token
from ..config import settings
from ..utils import now
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/api/auth")

class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@router.post("/register")
async def register(data: RegisterIn):
    if len(data.password) < 8:
        raise HTTPException(400, "Password must contain at least 8 characters")
    email = data.email.lower().strip()
    if await users.find_one({"email": email}):
        raise HTTPException(409, "Email already registered")
    doc = {
        "name": data.name.strip()[:80],
        "email": email,
        "password_hash": hash_password(data.password),
        "role": "user",
        "plan": "free",
        "storage_limit": settings.free_storage,
        "used_storage": 0,
        "created_at": now()
    }
    try:
        result = await users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Email already registered")
    token = create_token(str(result.inserted_id))
    response = JSONResponse({"ok": True, "message": "Account created"})
    response.set_cookie("sst_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=86400, path="/")
    return response

@router.post("/login")
async def login(data: LoginIn):
    user = await users.find_one({"email": data.email.lower().strip()})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    if user.get("banned"):
        raise HTTPException(403, "Account is banned")
    token = create_token(str(user["_id"]), user.get("role", "user"))
    response = JSONResponse({"ok": True})
    response.set_cookie("sst_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=86400, path="/")
    return response

@router.post("/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("sst_session", path="/")
    return response

@router.get("/me")
async def me(request: Request):
    from bson import ObjectId
    from ..security import require_auth
    payload = require_auth(request)
    user = await users.find_one({"_id": ObjectId(payload["sub"])}, {"password_hash": 0})
    if not user:
        raise HTTPException(404, "User not found")
    user["_id"] = str(user["_id"])
    return {
        "name": user.get("name"),
        "email": user.get("email"),
        "role": user.get("role", "user"),
        "plan": user.get("plan", "free"),
        "used_storage": user.get("used_storage", 0),
        "storage_limit": user.get("storage_limit", 0),
        "admin_email": settings.admin_email,
        "account_expires_at": user.get("account_expires_at").isoformat() if user.get("account_expires_at") else None
    }

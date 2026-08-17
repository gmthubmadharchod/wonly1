import base64, hashlib, hmac, os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException, status

ALGO = "HS256"

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return "pbkdf2$310000$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()

def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt_b64, digest_b64 = stored.split("$", 3)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def create_token(user_id: str, role: str = "user", minutes: int = 1440) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "role": role, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, __import__("app.config", fromlist=["settings"]).settings.jwt_secret, algorithm=ALGO)

def decode_token(token: str):
    try:
        return jwt.decode(token, __import__("app.config", fromlist=["settings"]).settings.jwt_secret, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

def require_auth(request):
    token = request.cookies.get("sst_session")
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    return decode_token(token)

def require_admin(request):
    payload = require_auth(request)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload

def create_file_token(file_id: str, user_id: str, minutes: int = 60) -> str:
    now = datetime.now(timezone.utc)
    payload = {"typ": "file", "fid": file_id, "sub": user_id, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, __import__("app.config", fromlist=["settings"]).settings.jwt_secret, algorithm=ALGO)

def decode_file_token(token: str):
    try:
        data = jwt.decode(token, __import__("app.config", fromlist=["settings"]).settings.jwt_secret, algorithms=[ALGO])
        if data.get("typ") != "file":
            raise ValueError()
        return data
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired file link")

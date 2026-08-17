from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from .config import settings
from .db import users, files_col
from .security import hash_password
from .routes.auth import router as auth_router
from .routes.files import router as files_router
from .routes.folders import router as folders_router
from .routes.admin import router as admin_router
from .services.telegram_storage import telegram_storage
from .services.expiry_worker import expiry_loop
import asyncio

BASE = Path(__file__).resolve().parent
app = FastAPI(title=settings.app_name)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
app.include_router(auth_router)
app.include_router(files_router)
app.include_router(folders_router)
app.include_router(admin_router)

@app.on_event("startup")
async def startup():
    asyncio.create_task(expiry_loop())
    await users.create_index("email", unique=True)
    await users.create_index("telegram_user_id", sparse=True)
    await files_col.create_index([("owner_id", 1), ("created_at", -1)])

    if not await users.find_one({"email": settings.admin_email.lower()}):
        await users.insert_one({
            "name": "Administrator",
            "email": settings.admin_email.lower(),
            "password_hash": hash_password(settings.admin_password),
            "role": "admin",
            "plan": "premium",
            "storage_limit": settings.premium_storage,
            "used_storage": 0,
        })

@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "templates" / "login.html").read_text()

@app.get("/{page}.html", response_class=HTMLResponse)
async def pages(page: str):
    allowed = {"login","register","dashboard","admin"}
    if page not in allowed:
        return RedirectResponse("/")
    html = (BASE / "templates" / f"{page}.html").read_text().replace("ADMIN_EMAIL", settings.admin_email)
    return html

@app.get("/d/{token}")
async def signed_download(token: str):
    from .routes.files import _token_file
    from .services.telegram_storage import telegram_storage
    from fastapi.responses import FileResponse
    f = await _token_file(token)
    path = await telegram_storage.download_to_temp(f["telegram_message_id"], f.get("telegram_file_id"))
    return FileResponse(path, media_type=f.get("mime"), filename=f["name"])

@app.get("/s/{token}")
async def signed_stream(token: str):
    from .routes.files import _token_file
    from .services.telegram_storage import telegram_storage
    from fastapi.responses import FileResponse
    f = await _token_file(token)
    path = await telegram_storage.download_to_temp(f["telegram_message_id"], f.get("telegram_file_id"))
    return FileResponse(path, media_type=f.get("mime"), filename=f["name"])

@app.get("/p/{file_id}")
async def permanent_file_link(file_id: str):
    from bson import ObjectId
    from fastapi import HTTPException
    from fastapi.responses import RedirectResponse
    from .db import files_col
    from .utils import telegram_message_url
    try:
        f = await files_col.find_one({"_id": ObjectId(file_id), "deleted": False})
    except Exception:
        f = None
    if not f:
        raise HTTPException(404, "File not found")
    base = settings.public_base_url.strip().rstrip("/") or settings.app_url.rstrip("/")
    return RedirectResponse(f"{base}/api/files/{file_id}/download", status_code=307)

@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "sst-cloud"}


@app.get("/healthz/telegram")
async def telegram_health():
    try:
        await telegram_storage.start()
        return {"ok": True, "storage_chat_id": int(settings.storage_chat_id)}
    except Exception as e:
        return {"ok": False, "error": str(e), "storage_chat_id": settings.storage_chat_id}

@app.head("/")
async def head_root():
    return Response(status_code=200)

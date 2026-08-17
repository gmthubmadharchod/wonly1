import aiohttp
import tempfile
import os
import uuid
import time
import asyncio
from datetime import timezone
from pathlib import Path
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from ..db import users, files_col, folders
from ..security import require_auth, create_file_token, decode_file_token
from ..config import settings
from ..utils import now, new_id, safe_name, human_size, telegram_message_url
from ..services.telegram_storage import telegram_storage

router = APIRouter(prefix="/api/files")

_progress = {}
_progress_lock = asyncio.Lock()

async def _set_progress(job_id, phase, current=0, total=0, error=None):
    async with _progress_lock:
        _progress[job_id] = {
            "phase": phase,
            "current": int(current or 0),
            "total": int(total or 0),
            "percent": round((current / total) * 100, 1) if total else 0,
            "error": error,
            "updated": time.time(),
        }

async def _cleanup_progress():
    cutoff = time.time() - 1800
    async with _progress_lock:
        for k in list(_progress):
            if _progress[k].get("updated", 0) < cutoff:
                _progress.pop(k, None)

@router.get("")
async def list_files(request: Request, folder_id: str | None = None):
    payload = require_auth(request)
    uid = payload["sub"]
    q = {"owner_id": uid, "deleted": False}
    if folder_id:
        q["folder_id"] = folder_id
    else:
        q["$or"] = [{"folder_id": None}, {"folder_id": {"$exists": False}}]
    docs = []
    async for f in files_col.find(q).sort("created_at", -1):
        f["_id"] = str(f["_id"])
        docs.append({
            "id": f["_id"], "name": f["name"], "size": f["size"],
            "size_text": human_size(f["size"]), "mime": f.get("mime"),
            "folder_id": f.get("folder_id"), "created_at": f["created_at"].isoformat(), "expires_at": (f.get("expires_at").isoformat() if f.get("expires_at") else None),
            "download_url": f"/api/files/{f['_id']}/download",
            "stream_url": f"/api/files/{f['_id']}/stream"
        })
    return {"files": docs}

async def _owned_file(request: Request, file_id: str):
    from bson import ObjectId
    payload = require_auth(request)
    try:
        oid = ObjectId(file_id)
    except Exception:
        raise HTTPException(400, "Invalid file id")
    f = await files_col.find_one({"_id": oid, "owner_id": payload["sub"], "deleted": False})
    if not f:
        raise HTTPException(404, "File not found")
    expires = f.get("expires_at")
    if expires:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now():
            await files_col.update_one({"_id": oid}, {"$set": {"deleted": True, "expired": True}})
            raise HTTPException(410, "File has expired")
    return f

@router.get("/{file_id}/link")
async def create_links(request: Request, file_id: str):
    f = await _owned_file(request, file_id)
    token = create_file_token(file_id, f["owner_id"], settings.download_token_minutes)
    base = settings.public_base_url.strip().rstrip("/") or settings.app_url.rstrip("/")
    return {
        "expires_minutes": settings.download_token_minutes,
        "download_url": f"{base}/d/{token}",
        "stream_url": f"{base}/s/{token}"
    }

@router.get("/{file_id}/permanent-link")
async def permanent_link(request: Request, file_id: str):
    f = await _owned_file(request, file_id)
    from ..db import users
    from bson import ObjectId
    user = await users.find_one({"_id": ObjectId(f["owner_id"])})
    if not user or user.get("plan") == "free":
        raise HTTPException(403, "Permanent links are available for Premium users only")
    base = settings.public_base_url.strip() or settings.app_url.rstrip("/")
    return {
        "permanent": True,
        "url": f"{base}/p/{file_id}",
        "telegram_message_url": f.get("telegram_message_url")
    }

@router.get("/{file_id}/telegram-check")
async def telegram_check(request: Request, file_id: str):
    f = await _owned_file(request, file_id)
    try:
        await telegram_storage.start()
        if f.get("telegram_file_id"):
            return {"ok": True, "method": "file_id", "message_id": f.get("telegram_message_id")}
        msg = await telegram_storage.get_message(f["telegram_chat_id"], f["telegram_message_id"])
        return {"ok": bool(msg), "method": "message", "message_id": f.get("telegram_message_id")}
    except Exception as e:
        raise HTTPException(502, f"Telegram storage check failed: {e}")

@router.get("/{file_id}/download")
async def download(request: Request, file_id: str):
    f = await _owned_file(request, file_id)
    path = await telegram_storage.download_to_temp(f["telegram_message_id"], f.get("telegram_file_id"))
    return FileResponse(path, media_type=f.get("mime"), filename=f["name"])

@router.get("/{file_id}/stream")
async def stream(request: Request, file_id: str):
    # Telegram-backed streaming endpoint. It downloads the source to a temporary
    # file first, then lets the ASGI server stream the file to the client.
    f = await _owned_file(request, file_id)
    path = await telegram_storage.download_to_temp(f["telegram_message_id"], f.get("telegram_file_id"))
    return FileResponse(path, media_type=f.get("mime"), filename=f["name"])

@router.delete("/{file_id}")
async def delete_file(request: Request, file_id: str):
    from bson import ObjectId
    f = await _owned_file(request, file_id)
    await files_col.update_one({"_id": ObjectId(file_id)}, {"$set": {"deleted": True, "deleted_at": now()}})
    await users.update_one({"_id": ObjectId(request.state.user_id)} if hasattr(request.state, "user_id") else {"_id": ObjectId(f["owner_id"])}, {"$inc": {"used_storage": -f["size"]}})
    return {"ok": True}

async def _token_file(token: str):
    from bson import ObjectId
    payload = decode_file_token(token)
    try:
        f = await files_col.find_one({"_id": ObjectId(payload["fid"]), "owner_id": payload["sub"], "deleted": False})
    except Exception:
        f = None
    if not f:
        raise HTTPException(404, "File not found")
    expires = f.get("expires_at")
    if expires:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now():
            raise HTTPException(410, "File has expired")
    return f

@router.get("/public/{token}")
async def public_download(token: str):
    f = await _token_file(token)
    path = await telegram_storage.download_to_temp(f["telegram_message_id"], f.get("telegram_file_id"))
    return FileResponse(path, media_type=f.get("mime"), filename=f["name"])


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    folder_id: str | None = Form(None),
):
    payload = require_auth(request)
    uid = payload["sub"]
    user = await users.find_one({"_id": __import__("bson").ObjectId(uid)})
    if not user:
        raise HTTPException(401, "User not found")

    job_id = request.headers.get("X-Upload-ID") or uuid.uuid4().hex
    await _set_progress(job_id, "receiving", 0, 0)

    if folder_id:
        from bson import ObjectId
        try:
            foid = ObjectId(folder_id)
        except Exception:
            raise HTTPException(400, "Invalid folder id")
        folder = await folders.find_one({"_id": foid, "owner_id": uid, "deleted": False})
        if not folder:
            raise HTTPException(404, "Folder not found")

    name = safe_name(file.filename)
    total = 0
    tmp = tempfile.NamedTemporaryFile(prefix="sst-upload-", delete=False)
    tmp_path = tmp.name

    if not settings.storage_chat_id:
        raise HTTPException(503, "Telegram storage channel is not configured")

    try:
        with tmp:
            while True:
                chunk = await file.read(8 * 1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_file_size:
                    raise HTTPException(413, "Maximum individual file size is 2 GiB")
                if user.get("role") != "admin" and user["used_storage"] + total > user["storage_limit"]:
                    raise HTTPException(413, "Storage quota exceeded")
                tmp.write(chunk)
                await _set_progress(job_id, "receiving", total, 0)

        await _set_progress(job_id, "telegram_upload", 0, total)

        async def tg_progress(current, size):
            await _set_progress(job_id, "telegram_upload", current, size)

        tg = await telegram_storage.save_upload(
            tmp_path, name, f"SST Cloud | {name}", progress=tg_progress
        )

        doc = {
            "owner_id": uid, "name": name, "size": total,
            "mime": file.content_type or "application/octet-stream",
            "folder_id": folder_id,
            "telegram_message_id": tg["message_id"],
            "telegram_chat_id": tg["chat_id"],
            "telegram_file_id": tg["file_id"],
            "telegram_file_unique_id": tg["file_unique_id"],
            "telegram_message_url": telegram_message_url(tg["chat_id"], tg["message_id"]),
            "deleted": False, "created_at": now(),
            "expires_at": (
                None if user.get("role") == "admin" or user.get("plan") == "premium"
                else now() + __import__("datetime").timedelta(days=settings.free_expiry_days)
            ),
        }
        result = await files_col.insert_one(doc)
        await users.update_one({"_id": user["_id"]}, {"$inc": {"used_storage": total}})
        await _set_progress(job_id, "complete", total, total)
        return {"ok": True, "id": str(result.inserted_id), "name": name, "size": total, "job_id": job_id}
    except HTTPException as e:
        await _set_progress(job_id, "error", error=str(e.detail))
        raise
    except Exception as e:
        await _set_progress(job_id, "error", error=str(e))
        raise
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        await _cleanup_progress()

@router.get("/progress/{job_id}")
async def upload_progress(request: Request, job_id: str):
    require_auth(request)
    async with _progress_lock:
        p = _progress.get(job_id)
    if not p:
        return {"phase": "unknown", "current": 0, "total": 0, "percent": 0}
    return p

class URLImport(BaseModel):
    url: HttpUrl
    filename: str | None = None
    folder_id: str | None = None

@router.post("/import-url")
async def import_url(data: URLImport, request: Request):
    payload = require_auth(request)
    uid = payload["sub"]
    user = await users.find_one({"_id": __import__("bson").ObjectId(uid)})
    if not user:
        raise HTTPException(401, "User not found")

    if data.folder_id:
        from bson import ObjectId
        try:
            foid = ObjectId(data.folder_id)
        except Exception:
            raise HTTPException(400, "Invalid folder id")
        folder = await folders.find_one({"_id": foid, "owner_id": uid, "deleted": False})
        if not folder:
            raise HTTPException(404, "Folder not found")

    job_id = request.headers.get("X-Upload-ID") or uuid.uuid4().hex
    await _set_progress(job_id, "remote_download", 0, 0)
    tmp_path = None
    total = 0

    try:
        timeout = aiohttp.ClientTimeout(total=3600, connect=30, sock_read=120)
        async with aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": "SST-Cloud/1.0"}
        ) as session:
            async with session.get(str(data.url), allow_redirects=True) as resp:
                if resp.status >= 400:
                    raise HTTPException(400, f"Remote server returned HTTP {resp.status}")
                length = resp.headers.get("Content-Length")
                remote_total = int(length) if length and length.isdigit() else 0
                if remote_total > settings.max_file_size:
                    raise HTTPException(413, "Remote file exceeds maximum size")

                fd, tmp_path = tempfile.mkstemp(prefix="sst-url-")
                os.close(fd)
                with open(tmp_path, "wb") as out:
                    async for chunk in resp.content.iter_chunked(8 * 1024 * 1024):
                        total += len(chunk)
                        if total > settings.max_file_size:
                            raise HTTPException(413, "Remote file exceeds maximum size")
                        if user.get("role") != "admin" and user["used_storage"] + total > user["storage_limit"]:
                            raise HTTPException(413, "Storage quota exceeded")
                        out.write(chunk)
                        await _set_progress(job_id, "remote_download", total, remote_total)

        name = safe_name(data.filename or os.path.basename(str(data.url).split("?")[0]) or "remote-file")
        await _set_progress(job_id, "telegram_upload", 0, total)

        async def tg_progress(current, size):
            await _set_progress(job_id, "telegram_upload", current, size)

        tg = await telegram_storage.save_upload(
            tmp_path, name, f"SST Cloud | {name}", progress=tg_progress
        )

        doc = {
            "owner_id": uid, "name": name, "size": total,
            "mime": "application/octet-stream", "folder_id": data.folder_id,
            "telegram_message_id": tg["message_id"], "telegram_chat_id": tg["chat_id"],
            "telegram_file_id": tg.get("file_id"), "telegram_file_unique_id": tg.get("file_unique_id"),
            "telegram_message_url": telegram_message_url(tg["chat_id"], tg["message_id"]),
            "deleted": False, "created_at": now(),
            "expires_at": (
                None if user.get("role") == "admin" or user.get("plan") == "premium"
                else now() + __import__("datetime").timedelta(days=settings.free_expiry_days)
            ),
        }
        result = await files_col.insert_one(doc)
        await users.update_one({"_id": user["_id"]}, {"$inc": {"used_storage": total}})
        await _set_progress(job_id, "complete", total, total)
        return {"ok": True, "id": str(result.inserted_id), "name": name, "size": total, "job_id": job_id}
    except HTTPException as e:
        await _set_progress(job_id, "error", error=str(e.detail))
        raise
    except Exception as e:
        await _set_progress(job_id, "error", error=str(e))
        raise
    finally:
        if tmp_path:
            try: os.remove(tmp_path)
            except OSError: pass
        await _cleanup_progress()

@router.patch("/{file_id}")
async def rename_file(request: Request, file_id: str, data: dict):
    f = await _owned_file(request, file_id)
    name = safe_name(str(data.get("name", "")).strip())
    if not name:
        raise HTTPException(400, "Invalid filename")
    from bson import ObjectId
    await files_col.update_one({"_id": ObjectId(file_id)}, {"$set": {"name": name}})
    return {"ok": True, "name": name}

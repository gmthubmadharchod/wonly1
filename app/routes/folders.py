from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from ..db import folders, files_col
from ..security import require_auth
from ..utils import now

router = APIRouter(prefix="/api/folders")

class FolderIn(BaseModel):
    name: str
    parent_id: str | None = None

@router.get("")
async def list_folders(request: Request):
    p = require_auth(request)
    docs = []
    async for x in folders.find({"owner_id": p["sub"], "deleted": False}).sort("name", 1):
        docs.append({"id": str(x["_id"]), "name": x["name"], "parent_id": x.get("parent_id")})
    return {"folders": docs}

@router.post("")
async def create_folder(request: Request, data: FolderIn):
    p = require_auth(request)
    name = data.name.strip()[:120]
    if not name:
        raise HTTPException(400, "Folder name is required")
    r = await folders.insert_one({"owner_id": p["sub"], "name": name, "parent_id": data.parent_id, "deleted": False, "created_at": now()})
    return {"ok": True, "id": str(r.inserted_id), "name": name}

@router.patch("/{folder_id}")
async def rename_folder(request: Request, folder_id: str, data: dict):
    payload = require_auth(request)
    from bson import ObjectId
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 100:
        raise HTTPException(400, "Invalid folder name")
    try: oid = ObjectId(folder_id)
    except Exception: raise HTTPException(400, "Invalid folder id")
    result = await folders.update_one({"_id": oid, "owner_id": payload["sub"]}, {"$set": {"name": name, "updated_at": now()}})
    if not result.matched_count: raise HTTPException(404, "Folder not found")
    return {"ok": True}

@router.delete("/{folder_id}")
async def delete_folder(request: Request, folder_id: str):
    payload = require_auth(request)
    from bson import ObjectId
    try: oid = ObjectId(folder_id)
    except Exception: raise HTTPException(400, "Invalid folder id")
    result = await folders.delete_one({"_id": oid, "owner_id": payload["sub"]})
    if not result.deleted_count: raise HTTPException(404, "Folder not found")
    await files_col.update_many({"owner_id": payload["sub"], "folder_id": folder_id}, {"$set": {"folder_id": None}})
    return {"ok": True}

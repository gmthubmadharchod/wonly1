import asyncio
from ..db import files_col, users
from .telegram_storage import telegram_storage

async def expiry_loop():
    while True:
        try:
            from ..utils import now
            async for f in files_col.find({
                "deleted": False,
                "expires_at": {"$ne": None, "$lte": now()}
            }).limit(100):
                try:
                    await telegram_storage.delete_storage_message(f["telegram_message_id"])
                except Exception:
                    pass
                await files_col.update_one(
                    {"_id": f["_id"]},
                    {"$set": {"deleted": True, "expired_at": now()}}
                )
                await users.update_one(
                    {"_id": __import__("bson").ObjectId(f["owner_id"])},
                    {"$inc": {"used_storage": -int(f.get("size", 0))}}
                )
        except Exception:
            pass
        await asyncio.sleep(300)

from datetime import timedelta
from bson import ObjectId
from ..db import files_col
from ..utils import now

async def set_expiry(owner, plan, created_at=None):
    from ..config import settings
    if plan == "premium":
        return None
    return (created_at or now()) + timedelta(days=settings.free_expiry_days)

async def file_doc_for_message(owner_id, msg, name, size, mime, folder_id=None, plan="free", chat_id=None):
    from ..utils import telegram_message_url
    from ..config import settings
    chat = int(chat_id or settings.storage_chat_id)
    created = now()
    expires = None if plan == "premium" else created + timedelta(days=settings.free_expiry_days)
    media = msg.document or msg.video or msg.audio or msg.photo
    return {
        "owner_id": str(owner_id),
        "name": name,
        "size": int(size or 0),
        "mime": mime or "application/octet-stream",
        "folder_id": folder_id,
        "telegram_message_id": msg.id,
        "telegram_chat_id": chat,
        "telegram_file_id": getattr(media, "file_id", None) if media else None,
        "telegram_file_unique_id": getattr(media, "file_unique_id", None) if media else None,
        "telegram_message_url": telegram_message_url(chat, msg.id),
        "deleted": False,
        "created_at": created,
        "expires_at": expires,
    }

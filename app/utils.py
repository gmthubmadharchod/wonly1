import os, secrets
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc)

def new_id():
    return secrets.token_urlsafe(16)

def safe_name(name: str) -> str:
    name = os.path.basename(name or "file")
    return "".join(c if c.isprintable() else "_" for c in name).strip()[:255] or "file"

def human_size(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return f"{x:.1f} {u}"
        x /= 1024

def telegram_message_url(chat_id: int, message_id: int) -> str:
    raw = str(chat_id)
    if raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{message_id}"
    return f"https://t.me/{raw}/{message_id}"

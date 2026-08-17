from pyrogram import Client
from ..config import settings


class TelegramStorage:
    def __init__(self):
        self.client = None
        self._lock = None
        self._storage_peer_ready = False
        self._storage_chat = None

    async def start(self):
        if self.client and self._storage_peer_ready and self._storage_chat:
            return

        from asyncio import Lock
        if self._lock is None:
            self._lock = Lock()

        async with self._lock:
            if self.client and self._storage_peer_ready and self._storage_chat:
                return

            bot_token = getattr(settings, "bot_token", "") or ""
            session_string = getattr(settings, "bot_session_string", "") or ""
            if not bot_token and not session_string:
                raise RuntimeError("Set BOT_TOKEN or BOT_SESSION_STRING.")
            if not settings.telegram_api_id or not settings.telegram_api_hash:
                raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required.")
            if not settings.storage_chat_id:
                raise RuntimeError("STORAGE_CHAT_ID is not configured.")

            kwargs = {
                "name": "sst_storage",
                "api_id": settings.telegram_api_id,
                "api_hash": settings.telegram_api_hash,
                "workdir": "/app/data",
            }
            if session_string:
                kwargs["session_string"] = session_string
            else:
                kwargs["bot_token"] = bot_token

            client = Client(**kwargs)
            try:
                await client.start()
                me = await client.get_me()
                if me is None:
                    raise RuntimeError("Telegram authentication returned no user.")

                target = int(settings.storage_chat_id)

                # STORAGE_CHAT_ID is treated as the actual Telegram chat ID.
                # Resolve it once and retain the Chat object. This prevents
                # Pyrogram from repeatedly trying to resolve the raw -100...
                # integer through an empty SQLite peer cache.
                try:
                    chat = await client.get_chat(target)
                except Exception as e:
                    raise RuntimeError(
                        f"Cannot access Telegram storage chat {target}. "
                        "Check STORAGE_CHAT_ID and make sure the bot is an "
                        "administrator/member of the private channel."
                    ) from e

                if not chat or int(chat.id) != target:
                    raise RuntimeError(f"Telegram storage chat {target} could not be resolved.")

                self._storage_chat = chat

            except Exception:
                try:
                    await client.stop()
                except Exception:
                    pass
                raise

            self.client = client
            self._storage_peer_ready = True

    async def stop(self):
        if self.client:
            await self.client.stop()
            self.client = None
        self._storage_peer_ready = False
        self._storage_chat = None

    async def get_message(self, chat_id, message_id):
        await self.start()
        return await self.client.get_messages(
            chat_id if chat_id else self._storage_chat,
            int(message_id),
        )

    async def copy_message(self, from_chat_id, message_id, to_chat_id=None):
        await self.start()
        return await self.client.copy_message(
            chat_id=to_chat_id or self._storage_chat,
            from_chat_id=int(from_chat_id),
            message_id=int(message_id),
        )

    async def save_upload(self, local_path, filename="", caption="", mime_type=None, progress=None):
        await self.start()

        async def _progress(current, total):
            if progress:
                result = progress(current, total)
                if hasattr(result, "__await__"):
                    await result

        msg = await self.client.send_document(
            chat_id=self._storage_chat,
            document=local_path,
            file_name=filename or None,
            caption=caption or None,
            disable_notification=True,
            progress=_progress if progress else None,
        )

        media = msg.document or msg.video or msg.audio or msg.photo
        return {
            "message_id": msg.id,
            "chat_id": msg.chat.id,
            "file_id": getattr(media, "file_id", None),
            "file_unique_id": getattr(media, "file_unique_id", None),
        }

    async def send_document(self, local_path, caption=""):
        return await self.save_upload(local_path, caption=caption)

    async def download_to_temp(self, message_id=None, file_id=None, progress=None):
        await self.start()

        async def _progress(current, total):
            if progress:
                result = progress(current, total)
                if hasattr(result, "__await__"):
                    await result

        media = file_id
        if not media:
            msg = await self.client.get_messages(self._storage_chat, int(message_id))
            if not msg:
                raise RuntimeError("Telegram storage message not found.")
            media = msg.document or msg.video or msg.audio or msg.photo
            if not media:
                raise RuntimeError("Telegram message contains no downloadable media.")

        return await self.client.download_media(
            media,
            progress=_progress if progress else None,
        )

    async def delete_storage_message(self, message_id):
        await self.start()
        await self.client.delete_messages(self._storage_chat, int(message_id))


telegram_storage = TelegramStorage()

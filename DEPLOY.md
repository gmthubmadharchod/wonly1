# SST Cloud PRO deployment

Use one Koyeb Web Service with the main Dockerfile.

Required Telegram environment variables:
- BOT_TOKEN
- TELEGRAM_API_ID
- TELEGRAM_API_HASH
- STORAGE_CHAT_ID
- BOT_SESSION_STRING may be blank in BOT_TOKEN mode

The storage bot must be an administrator in the private storage channel. BOT_TOKEN is persistent; normal web-service restarts do not require posting a new message to the channel. The app recreates and authenticates the Pyrogram client on demand.

The web service includes normal upload, direct URL import, chunked receiving, progress UI, folders, file rename/delete, temporary signed links, and Premium permanent links.

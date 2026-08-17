# SST Cloud — Final Pro

Production-oriented Telegram-backed cloud starter.

## What it does

- Modern responsive login/register/dashboard/admin UI
- User login with email + password
- Telegram bot login with the same email + password
- Persistent Telegram↔SST account binding in MongoDB
- Private Telegram channel as binary storage
- MongoDB as metadata/index
- Admin/owner unlimited quota
- Free quota + free-file expiry
- Premium quota + no expiry
- 2 GiB max individual file size
- `/folder`
- `/insert CHANNEL_ID START-END` with configurable 3-second delay
- Bot direct upload/copy into storage
- Web upload/copy into storage
- Admin user/plan/statistics dashboard
- Premium permanent SST links that redirect to the Telegram message
- Authenticated download and stream endpoints
- Docker deployment
- Render/Koyeb `$PORT` compatibility
- `/healthz`
- Bot replies use `parse_mode=None` so filenames/user text cannot break Markdown/HTML parsing

## Important architecture

Telegram performs the channel-to-channel `copy_message` operation. The application does not download an `/insert` source file to local disk and re-upload it.

However, no honest architecture can promise zero server bandwidth for browser streaming/resumable HTTP downloads while also serving bytes through an arbitrary custom website URL. Telegram private-media URLs are not permanent public CDN URLs.

SST therefore separates:
- Premium permanent link: stable SST URL -> Telegram message redirect, minimum SST bandwidth.
- Download/stream API: SST authenticates the user and fetches the Telegram media, so this path consumes server egress.

## Bot

- `/register email password`
- `/login email password`
- `/logout`
- `/me`
- `/folder Folder Name`
- `/insert CHANNEL_ID START-END` (admin only)
- Send document/video/audio/photo after login

The bot session is persisted in MongoDB by `telegram_user_id`, so normal restarts do not require another login.

## Deployment

### Render
Use two services from the same repository:
1. Web Service: `Dockerfile`
2. Background Worker: `bot.Dockerfile`

Set the same environment variables. The web service binds to `0.0.0.0:$PORT`.

### Koyeb
Use two services:
1. Web service with `Dockerfile`
2. Bot worker/service with `bot.Dockerfile`

MongoDB should be external (for example MongoDB Atlas) for free-tier deployments.

## Environment

Copy `.env.example` to `.env` and set:
- `MONGO_URI`
- `MONGO_DB`
- `JWT_SECRET`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `BOT_TOKEN`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `STORAGE_CHAT_ID`
- `BOT_SESSION_STRING` (recommended for a dedicated Telegram storage account)
- `APP_URL` / `PUBLIC_BASE_URL`
- quota/expiry/delay settings

Never commit `.env`.

## Telegram permissions

The storage account must be able to access the private storage channel. The account used for `/insert` must also be able to read the source channel. Telegram permissions/API access are authoritative; being an admin in one chat does not automatically grant access to another chat.


Free file stream/download availability ends when the file expires and its Telegram storage message is removed. Premium files have no expiry by default. A stream URL is therefore not a way to bypass file expiry.


## Telegram session string

`BOT_SESSION_STRING` is an optional Pyrogram MTProto user-session string. It is NOT the BotFather token.
- `BOT_TOKEN` authenticates the Telegram bot.
- `BOT_SESSION_STRING` authenticates a dedicated Telegram user account through Pyrogram.
For a storage/import system, a dedicated storage account session is recommended when Telegram API capabilities require a user account. Treat the session string exactly like a password: never publish it or commit it to Git.

## Super Admin controls

The owner can:
- Search and inspect any account.
- Promote/demote Premium.
- Set any user's exact storage quota in GB.
- Set Free/Premium quota defaults.
- Set an individual user's expiry policy.
- Ban/unban accounts.
- View account metadata, file count and storage used.
- See total users, Premium users, files and aggregate storage.


## Admin Settings
The owner can change from the web admin panel:
- Admin email
- Admin password
- Default Free storage
- Default Premium storage
- Free expiry days
- Maximum per-user quota

The values are stored in MongoDB so they persist across Render/Koyeb restarts. Environment variables remain useful as bootstrap/fallback defaults.


### Web upload fix
Web uploads are received into a temporary file, then `TelegramStorage.save_upload()` sends that file to the private Telegram storage channel and returns normalized Telegram message/file metadata.


## Web-only build
No Telegram bot polling or bot command runtime is included. Telegram is used only as the storage backend for the website.

## Import URL
Dashboard → **Import URL** accepts a direct HTTP/HTTPS file URL. The server downloads the remote file to a temporary file, uploads it to the private Telegram storage channel, stores metadata in MongoDB, then deletes the temporary file. This is a direct URL importer, not an rclone client; login/JS/CAPTCHA/protected webpage URLs are not guaranteed.

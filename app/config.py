from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "SST Cloud"
    app_url: str = "http://localhost:8000"
    public_base_url: str = ""
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "sst_cloud"
    jwt_secret: str = "CHANGE_ME"
    admin_email: str = "admin@example.com"
    admin_password: str = "CHANGE_ME"
    bot_token: str = ""
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    bot_session_string: str = ""
    storage_chat_id: str = ""
    max_file_size: int = 2 * 1024 * 1024 * 1024
    free_storage: int = 5 * 1024 * 1024 * 1024
    premium_storage: int = 50 * 1024 * 1024 * 1024
    download_token_minutes: int = 60
    free_expiry_days: int = 30
    insert_delay_seconds: float = 3.0
    admin_default_storage: int = 0
    max_admin_storage: int = 10 * 1024 * 1024 * 1024 * 1024
    cookie_secure: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

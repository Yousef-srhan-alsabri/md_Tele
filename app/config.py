from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "منصة إدارة حسابات Telegram"
    environment: str = "production"
    secret_key: str = Field(min_length=32)
    session_encryption_key: str
    database_url: str
    telegram_api_id: int
    telegram_api_hash: str
    admin_username: str = "admin"
    admin_password: str = Field(min_length=8)
    public_registration: bool = True
    default_user_balance: int = 0
    max_links_per_batch: int = 500
    max_accounts_per_user: int = 10
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://") and "+psycopg" not in url:
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

@lru_cache
def get_settings() -> Settings:
    return Settings()

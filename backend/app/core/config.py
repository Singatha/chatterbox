from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chatterbox API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://chat:chat_dev_password@localhost:5432/chat"
    jwt_secret: str = Field(default="development-secret-change-me-32-characters", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    redis_url: str = "redis://localhost:6379/0"
    redis_required: bool = False
    redis_key_prefix: str = "chatterbox"
    presence_ttl_seconds: int = Field(default=30, ge=5)
    presence_heartbeat_seconds: int = Field(default=10, ge=1)
    typing_ttl_seconds: float = Field(default=5.0, ge=1.0)
    realtime_sweep_interval_seconds: float = Field(default=1.0, ge=0.1)
    realtime_rate_limit_window_seconds: int = Field(default=60, ge=1)
    message_send_rate_limit: int = Field(default=30, ge=1)
    typing_rate_limit: int = Field(default=120, ge=1)
    receipt_rate_limit: int = Field(default=120, ge=1)

    @model_validator(mode="after")
    def validate_realtime_intervals(self) -> "Settings":
        if self.presence_heartbeat_seconds >= self.presence_ttl_seconds:
            raise ValueError("Presence heartbeat must be shorter than its TTL")
        return self

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

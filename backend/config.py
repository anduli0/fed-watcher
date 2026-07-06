from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List
import uuid, sys


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str = ""  # no longer required — Claude CLI handles auth
    FRED_API_KEY: str = ""
    JWT_SECRET: str = ""
    ADMIN_PASSWORD_HASH: str = ""
    OWNER_MAC: str = ""
    ALLOWED_IPS: str = "127.0.0.1"
    MODEL_ID: str = "claude-sonnet-4-6"
    # Set DEV_MODE=true in .env to skip MAC/JWT validation during development
    DEV_MODE: bool = False
    # Telegram push (daily brief + derivation report). Optional — telegram is a
    # no-op when unset. Declared here so settings.TELEGRAM_* resolve (extra=ignore
    # would otherwise drop them and raise AttributeError in telegram_notify).
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_must_be_set(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def allowed_ip_list(self) -> List[str]:
        return [ip.strip() for ip in self.ALLOWED_IPS.split(",")]

    @property
    def jwt_ready(self) -> bool:
        return len(self.JWT_SECRET) >= 32


settings = Settings()

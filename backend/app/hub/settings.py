"""Hub settings (environment driven, safe defaults for local development)."""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class HubSettings(BaseSettings):
    """All hub configuration. Every value can be overridden through the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    # Shared with the main SafeR API
    SECRET_KEY: str = "change-me-safer-hub-dev-secret"
    DATABASE_URL: Optional[str] = None

    # Hub specific
    HUB_DATABASE_URL: Optional[str] = None
    HUB_ENCRYPTION_KEY: Optional[str] = None
    HUB_TOKEN_TTL_DAYS: int = 30
    HUB_POLL_INTERVAL: int = 30
    HUB_SIA_PORT: int = 0
    HUB_SIA_ACCOUNTS: str = ""  # comma separated "account:home_id" pairs
    HUB_WEATHER_ENABLED: bool = True
    HUB_DEMO_ENABLED: bool = True
    HUB_HTTP_TIMEOUT: float = 10.0
    HUB_ALLOW_OPEN_REGISTRATION: bool = True

    # Brand integrations
    MATTER_SERVER_URL: str = "ws://localhost:5580/ws"
    SAFER_INCIDENTS_URL: str = ""  # e.g. https://api.safer-ci.app/api/v1/incidents/
    SAFER_INCIDENTS_TOKEN: str = ""

    @property
    def database_url(self) -> str:
        """Resolve the database URL (hub specific > shared > local sqlite)."""
        return self.HUB_DATABASE_URL or self.DATABASE_URL or "sqlite+aiosqlite:///./safer_hub.db"

    @property
    def encryption_key(self) -> bytes:
        """Fernet key used to encrypt device credentials at rest."""
        if self.HUB_ENCRYPTION_KEY:
            return self.HUB_ENCRYPTION_KEY.encode()
        digest = hashlib.sha256(("safer-hub:" + self.SECRET_KEY).encode()).digest()
        return base64.urlsafe_b64encode(digest)

    @property
    def sia_accounts(self) -> dict:
        """Parse HUB_SIA_ACCOUNTS into {account: home_id}."""
        result = {}
        for pair in self.HUB_SIA_ACCOUNTS.split(","):
            pair = pair.strip()
            if ":" in pair:
                account, home_id = pair.split(":", 1)
                result[account.strip().upper()] = home_id.strip()
        return result


@lru_cache(maxsize=1)
def get_settings() -> HubSettings:
    """Cached settings instance."""
    return HubSettings()

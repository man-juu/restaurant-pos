"""Settings read from environment variables (12-factor). No secrets have defaults outside dev."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, PostgresDsn


class Settings(BaseModel):
    environment: Literal["dev", "test", "staging", "production"] = "dev"
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://pos_owner:dev-only-password@localhost:5432/pos")
    )
    # Owner role for Alembic. Unset means "same as database_url" (fine only for local dev).
    migration_database_url: PostgresDsn | None = None
    db_pool_size: int = Field(default=5, ge=1, le=50)  # small VPS: keep connections few
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Sessions (docs/06 section 3). Platform limits; per-tenant idle override comes with
    # tenant settings (FR-IDN-009).
    session_idle_minutes: int = Field(default=60, ge=5, le=24 * 60)
    session_absolute_hours: int = Field(default=12, ge=1, le=24 * 30)
    # Lockout: after this many failures, delays grow exponentially (30 s, 60 s, ... max 15 min).
    login_max_failures: int = Field(default=5, ge=1, le=50)

    @property
    def migration_url(self) -> PostgresDsn:
        return self.migration_database_url or self.database_url

    @classmethod
    def from_env(cls) -> "Settings":
        # Maps APP-style names to fields, e.g. DATABASE_URL -> database_url.
        values = {
            name: os.environ[name.upper()]
            for name in cls.model_fields
            if name.upper() in os.environ
        }
        settings = cls.model_validate(values)
        if settings.environment in ("staging", "production") and "DATABASE_URL" not in os.environ:
            raise RuntimeError("DATABASE_URL must be set outside dev and test")
        return settings


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()

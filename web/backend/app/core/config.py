"""Application settings.

Single source of runtime configuration for the backend. Values come from the
process environment (and the repo-root ``.env`` in development); every variable
is documented in ``.env.example``. See ``docs/architecture.md`` for the data
layer and ``docs/workflow.md`` for the environment rules.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the environment. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    app_env: str = "development"
    secret_key: str = "change-me"

    # CORS — the frontend dev origin allowed to call the API.
    frontend_origin: str = "http://localhost:3000"

    # Core data stores.
    database_url: str = "postgresql+psycopg://velora:velora@localhost:5544/velora"
    redis_url: str = "redis://localhost:6379/0"

    # AI provider selection (the provider-agnostic interface lands in a later phase).
    llm_provider: str = "openai"
    openai_api_key: str = ""
    local_llm_base_url: str = "http://localhost:11434"

    @property
    def is_sqlite(self) -> bool:
        """True when pointed at SQLite (used by tests and the engine factory)."""
        return self.database_url.startswith("sqlite")

    @property
    def cors_origins(self) -> list[str]:
        """Allowed CORS origins.

        ``FRONTEND_ORIGIN`` may be a comma-separated list. The localhost/127.0.0.1
        counterpart of each origin is added automatically, since the dev server is
        reachable under both hostnames.
        """
        raw = [o.strip() for o in self.frontend_origin.split(",") if o.strip()]
        origins = set(raw)
        for origin in raw:
            if "localhost" in origin:
                origins.add(origin.replace("localhost", "127.0.0.1"))
            elif "127.0.0.1" in origin:
                origins.add(origin.replace("127.0.0.1", "localhost"))
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance (loaded once per process)."""
    return Settings()

"""Settings load from the environment and expose the SQLite predicate."""

from __future__ import annotations

from app.core.config import Settings, get_settings


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://example.test")
    settings = Settings()
    assert settings.database_url == "sqlite://"
    assert settings.frontend_origin == "http://example.test"


def test_is_sqlite_predicate():
    assert Settings(database_url="sqlite:///x.db").is_sqlite is True
    assert (
        Settings(database_url="postgresql+psycopg://u:p@localhost/db").is_sqlite is False
    )


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_cors_origins_adds_localhost_counterpart():
    s = Settings(frontend_origin="http://localhost:3000")
    assert "http://localhost:3000" in s.cors_origins
    assert "http://127.0.0.1:3000" in s.cors_origins


def test_cors_origins_accepts_comma_separated():
    s = Settings(frontend_origin="http://localhost:3000, https://app.example.com")
    assert "https://app.example.com" in s.cors_origins
    assert "http://127.0.0.1:3000" in s.cors_origins

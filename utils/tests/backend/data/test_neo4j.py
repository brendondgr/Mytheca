"""The Neo4j substrate client — graceful, lazy, and access-mode aware.

Runs fully offline: ``build_driver`` is monkeypatched to a recording fake, so no
container is needed. Proves the best-effort posture (``ping`` never raises) and
that read/write sessions request the correct Neo4j access mode (§7.4).
"""

from __future__ import annotations

import pytest

from app.core import neo4j as neo4j_mod
from app.core.config import Settings


class _FakeSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeDriver:
    def __init__(self, *, connectivity: bool = True):
        self._connectivity = connectivity
        self.sessions: list[_FakeSession] = []
        self.closed = False

    def verify_connectivity(self) -> None:
        if not self._connectivity:
            raise RuntimeError("server down")

    def session(self, **kwargs) -> _FakeSession:
        s = _FakeSession(**kwargs)
        self.sessions.append(s)
        return s

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_driver():
    """Forget any cached driver before and after each test (module global)."""
    neo4j_mod.close_driver()
    yield
    neo4j_mod.close_driver()


def _configure(monkeypatch, uri: str = "bolt://localhost:3349") -> None:
    monkeypatch.setattr(
        neo4j_mod,
        "get_settings",
        lambda: Settings(neo4j_uri=uri, neo4j_user="neo4j", neo4j_password="x"),
    )


def test_is_enabled_reflects_uri(monkeypatch):
    _configure(monkeypatch, "")
    assert neo4j_mod.is_enabled() is False
    _configure(monkeypatch, "bolt://localhost:3349")
    assert neo4j_mod.is_enabled() is True


def test_get_driver_is_none_when_disabled(monkeypatch):
    _configure(monkeypatch, "")
    assert neo4j_mod.get_driver() is None


def test_get_driver_is_cached_singleton(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(neo4j_mod, "build_driver", lambda: _FakeDriver())
    first = neo4j_mod.get_driver()
    assert first is not None
    assert neo4j_mod.get_driver() is first  # cached, not rebuilt


def test_ping_false_when_build_raises(monkeypatch):
    _configure(monkeypatch)

    def _boom():
        raise RuntimeError("no driver")

    monkeypatch.setattr(neo4j_mod, "build_driver", _boom)
    assert neo4j_mod.ping() is False  # graceful, never raises


def test_ping_false_when_disabled(monkeypatch):
    _configure(monkeypatch, "")
    assert neo4j_mod.ping() is False


def test_ping_true_when_connectivity_ok(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(neo4j_mod, "build_driver", lambda: _FakeDriver(connectivity=True))
    assert neo4j_mod.ping() is True


def test_ping_false_when_connectivity_down(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(neo4j_mod, "build_driver", lambda: _FakeDriver(connectivity=False))
    assert neo4j_mod.ping() is False


def test_read_session_opens_read_access_and_closes(monkeypatch):
    _configure(monkeypatch)
    fake = _FakeDriver()
    monkeypatch.setattr(neo4j_mod, "build_driver", lambda: fake)
    with neo4j_mod.read_session() as session:
        assert session.kwargs["default_access_mode"] == "READ"
    assert fake.sessions[-1].closed is True


def test_write_session_opens_write_access(monkeypatch):
    _configure(monkeypatch)
    fake = _FakeDriver()
    monkeypatch.setattr(neo4j_mod, "build_driver", lambda: fake)
    with neo4j_mod.write_session() as session:
        assert session.kwargs["default_access_mode"] == "WRITE"


def test_close_driver_resets_singleton(monkeypatch):
    _configure(monkeypatch)
    fake = _FakeDriver()
    monkeypatch.setattr(neo4j_mod, "build_driver", lambda: fake)
    neo4j_mod.get_driver()
    neo4j_mod.close_driver()
    assert fake.closed is True

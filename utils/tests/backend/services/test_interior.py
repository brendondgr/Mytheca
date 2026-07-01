"""Per-character interior state (best-effort Redis): roundtrip, overwrite, disabled no-op."""

from __future__ import annotations

from app.memory import interior
from app.memory.interior import InteriorRecord


class _FakeRedis:
    """Minimal in-memory stand-in for the string ops interior state uses."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)


def test_set_and_get_roundtrip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    rec = InteriorRecord(
        character_id="mei",
        disposition="Guarded — I want the coin without the strings.",
        retrospective="He pushed; I held.",
        branch_dispositions={"escalate": "Then I walk.", "de-escalate": "Then we talk terms."},
        seq=4,
    )
    interior.set_interior("ps1", "mei", rec)
    got = interior.get_interior("ps1", "mei")
    assert got is not None
    assert got.disposition == rec.disposition
    assert got.retrospective == "He pushed; I held."
    assert got.branch_dispositions["escalate"] == "Then I walk."
    assert got.seq == 4


def test_set_overwrites_previous(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    interior.set_interior("ps1", "mei", InteriorRecord(character_id="mei", disposition="wary"))
    interior.set_interior("ps1", "mei", InteriorRecord(character_id="mei", disposition="warmer"))
    got = interior.get_interior("ps1", "mei")
    assert got is not None and got.disposition == "warmer"


def test_get_absent_is_none(monkeypatch):
    monkeypatch.setattr(interior, "_redis", lambda: _FakeRedis())
    assert interior.get_interior("ps1", "ghost") is None


def test_scoped_per_session_and_character(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    interior.set_interior("ps1", "mei", InteriorRecord(character_id="mei", disposition="a"))
    assert interior.get_interior("ps2", "mei") is None  # different session
    assert interior.get_interior("ps1", "kira") is None  # different character


def test_disabled_is_a_clean_noop():
    # The autouse conftest fixture blanks REDIS_URL → _redis() returns None.
    interior.set_interior("ps1", "mei", InteriorRecord(character_id="mei", disposition="x"))
    assert interior.get_interior("ps1", "mei") is None

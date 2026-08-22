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

    def scan_iter(self, match: str = "*", count: int | None = None):
        prefix = match.rstrip("*")
        return [k for k in list(self.store) if k.startswith(prefix)]

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += 1 if self.store.pop(key, None) is not None else 0
        return removed


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


# ---- clearing (a rewind's forgetting) --------------------------------------


def test_clear_session_removes_every_character_in_that_session(monkeypatch):
    """The reason this function exists: a rewind cuts the beats, and without this the cast
    walks back into the scene still carrying the stance those beats produced. The
    transcript forgets and the characters do not, which is what "it didn't forget" looks
    like from the player's chair."""
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    interior.set_interior("ps1", "mei", InteriorRecord(character_id="mei", disposition="a"))
    interior.set_interior("ps1", "kira", InteriorRecord(character_id="kira", disposition="b"))

    assert interior.clear_session("ps1") == 2

    assert interior.get_interior("ps1", "mei") is None
    assert interior.get_interior("ps1", "kira") is None


def test_clear_session_leaves_other_play_throughs_alone(monkeypatch):
    """A rewind is scoped to one play-through. A branch of the same scenario, or the
    snapshot the rewind just forked, must keep its own cast state."""
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    interior.set_interior("ps1", "mei", InteriorRecord(character_id="mei", disposition="a"))
    interior.set_interior("ps2", "mei", InteriorRecord(character_id="mei", disposition="b"))

    interior.clear_session("ps1")

    assert interior.get_interior("ps1", "mei") is None
    got = interior.get_interior("ps2", "mei")
    assert got is not None and got.disposition == "b"


def test_clear_session_is_not_fooled_by_a_session_id_that_is_a_prefix(monkeypatch):
    """``interior:ps1:*`` must not match ``interior:ps10:mei``. Ids are opaque strings and
    nothing stops one being a prefix of another."""
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    interior.set_interior("ps1", "mei", InteriorRecord(character_id="mei", disposition="a"))
    interior.set_interior("ps10", "mei", InteriorRecord(character_id="mei", disposition="b"))

    interior.clear_session("ps1")

    assert interior.get_interior("ps10", "mei") is not None


def test_clear_session_on_an_empty_session_is_zero(monkeypatch):
    monkeypatch.setattr(interior, "_redis", lambda: _FakeRedis())
    assert interior.clear_session("ps-empty") == 0


def test_clear_session_without_redis_is_a_clean_noop():
    """The autouse conftest fixture blanks REDIS_URL. A rewind must not depend on Redis
    being up — every other store in the mutation path is best-effort too."""
    assert interior.clear_session("ps1") == 0

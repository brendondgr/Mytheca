"""Recent-turn buffer (best-effort Redis): roundtrip, cap, disabled no-op."""

from __future__ import annotations

from app.memory import buffer


class _FakeRedis:
    """Minimal in-memory stand-in for the Redis list ops the buffer uses."""

    def __init__(self) -> None:
        self.store: dict[str, list[str]] = {}

    def lpush(self, key: str, *vals: str) -> int:
        lst = self.store.setdefault(key, [])
        for v in vals:
            lst.insert(0, v)
        return len(lst)

    def ltrim(self, key: str, start: int, end: int) -> None:
        lst = self.store.get(key, [])
        self.store[key] = lst[start:] if end == -1 else lst[start : end + 1]

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        lst = self.store.get(key, [])
        return lst[start:] if end == -1 else lst[start : end + 1]

    def expire(self, key: str, ttl: int) -> None:  # noqa: D401 - no-op
        pass

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


def test_push_and_recent_roundtrip_chronological(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    buffer.push_turn("ps1", "player", "I slide the pouch.")
    buffer.push_turn("ps1", "character", "Coin's easy.", character_id="mei")
    beats = buffer.recent_turns("ps1")
    assert [b["text"] for b in beats] == ["I slide the pouch.", "Coin's easy."]
    assert beats[1]["role"] == "character" and beats[1]["characterId"] == "mei"


def test_buffer_caps_at_turn_buffer_size(monkeypatch):
    from app.core.config import get_settings

    fake = _FakeRedis()
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    cap = get_settings().turn_buffer_size  # retention ceiling (must be ≥ max context_beats=100)
    for i in range(cap + 30):
        buffer.push_turn("ps1", "narrator", f"beat {i}")
    beats = buffer.recent_turns("ps1", limit=cap + 100)
    assert len(beats) == cap  # retention capped at Settings.turn_buffer_size
    assert beats[-1]["text"] == f"beat {cap + 29}"  # newest retained


def test_recent_turns_honors_an_explicit_fetch_limit(monkeypatch):
    # The assembler fetches exactly the scene's context_beats — the newest N, chronological.
    fake = _FakeRedis()
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    for i in range(20):
        buffer.push_turn("ps1", "narrator", f"beat {i}")
    beats = buffer.recent_turns("ps1", limit=5)
    assert [b["text"] for b in beats] == [f"beat {i}" for i in range(15, 20)]


def test_clear_drops_session(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    buffer.push_turn("ps1", "player", "x")
    buffer.clear("ps1")
    assert buffer.recent_turns("ps1") == []


def test_disabled_is_a_clean_noop():
    # The autouse conftest fixture blanks REDIS_URL → _redis() returns None.
    buffer.push_turn("ps1", "player", "x")
    assert buffer.recent_turns("ps1") == []

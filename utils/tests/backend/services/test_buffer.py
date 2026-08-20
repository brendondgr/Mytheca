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

    def llen(self, key: str) -> int:
        return len(self.store.get(key, []))

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


# ---- Anchored window (prompt-cache prefix stability) ------------------------
# A plain "last N beats" window drops its oldest beat every turn, which changes the first
# line of the rendered transcript. A prefix cache matches from the first token, so that
# one dropped line throws away every cached token behind it. Anchoring the START to a
# multiple of `block` holds the prefix still for `block` beats at a time.


def _fill(monkeypatch, n: int) -> "_FakeRedis":
    fake = _FakeRedis()
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    for i in range(n):
        buffer.push_turn("ps1", "player", f"beat {i}")
    return fake


def test_anchored_window_returns_everything_below_the_window(monkeypatch):
    _fill(monkeypatch, 6)
    beats = buffer.anchored_turns("ps1", window=10, block=4)
    assert [b["text"] for b in beats] == [f"beat {i}" for i in range(6)]


def test_anchored_window_start_holds_still_between_blocks(monkeypatch):
    """The whole point: the first beat must not move on every push."""
    fake = _fill(monkeypatch, 20)
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    first = buffer.anchored_turns("ps1", window=10, block=5)[0]["text"]
    for _ in range(4):
        buffer.push_turn("ps1", "player", "another")
        assert buffer.anchored_turns("ps1", window=10, block=5)[0]["text"] == first


def test_anchored_window_re_anchors_a_whole_block_at_a_time(monkeypatch):
    fake = _fill(monkeypatch, 20)
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    before = buffer.anchored_turns("ps1", window=10, block=5)
    for _ in range(5):
        buffer.push_turn("ps1", "player", "another")
    after = buffer.anchored_turns("ps1", window=10, block=5)
    assert after[0]["text"] != before[0]["text"]
    # It jumped by a whole block, not by one beat.
    assert before[5]["text"] == after[0]["text"]


def test_anchored_window_never_drops_below_the_requested_depth(monkeypatch):
    fake = _fill(monkeypatch, 37)
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    for _ in range(12):
        beats = buffer.anchored_turns("ps1", window=10, block=5)
        assert 10 <= len(beats) <= 15  # window .. window + block
        buffer.push_turn("ps1", "player", "another")


def test_anchored_window_block_of_one_is_a_plain_sliding_window(monkeypatch):
    """The rollback path has to behave exactly as before."""
    fake = _fill(monkeypatch, 20)
    monkeypatch.setattr(buffer, "_redis", lambda: fake)
    assert buffer.anchored_turns("ps1", window=10, block=1) == buffer.recent_turns("ps1", limit=10)


def test_anchored_window_is_empty_without_redis(monkeypatch):
    monkeypatch.setattr(buffer, "_redis", lambda: None)
    assert buffer.anchored_turns("ps1", window=10, block=5) == []

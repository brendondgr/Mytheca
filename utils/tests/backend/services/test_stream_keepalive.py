"""``events.stream.with_keepalive`` — keeping a long generation's socket warm.

An agent turn calls the LLM to completion before its first ``yield``, so the response
holds a byte-for-byte silent socket for the whole generation (measured: 24s for one
storyline turn; minutes on a large local reasoning model). Response headers go out
immediately, so nothing on the wire says the work is alive and any idle-connection
reaping takes the stream down mid-thought — surfacing in the UI as a connection
failure while the model is demonstrably still generating.
"""

from __future__ import annotations

import time

import pytest

from app.events.stream import with_keepalive


def _ping() -> str:
    return "ping"


def test_a_fast_source_needs_no_keepalives():
    out = list(with_keepalive(iter([1, 2, 3]), _ping, interval=5.0))
    assert out == [1, 2, 3]


def test_an_empty_source_ends_without_emitting_anything():
    assert list(with_keepalive(iter([]), _ping, interval=5.0)) == []


def test_a_slow_source_is_padded_with_keepalives_until_its_item_arrives():
    def slow():
        time.sleep(0.25)
        yield "result"

    out = list(with_keepalive(slow(), _ping, interval=0.05))
    assert out[-1] == "result"
    assert out[:-1], "the idle gap before the item must be filled with keep-alives"
    assert set(out[:-1]) == {"ping"}


def test_items_keep_their_order_around_the_keepalives():
    def paced():
        yield "a"
        time.sleep(0.2)
        yield "b"

    out = list(with_keepalive(paced(), _ping, interval=0.05))
    assert [x for x in out if x != "ping"] == ["a", "b"]
    # The gap is *between* a and b, so at least one keep-alive lands there.
    assert out.index("a") < out.index("ping") < out.index("b")


def test_an_exception_is_re_raised_on_the_consuming_thread():
    """The route turns APIError into a terminal error frame — that must still work."""

    def boom():
        yield "first"
        raise ValueError("upstream died")

    gen = with_keepalive(boom(), _ping, interval=5.0)
    assert next(gen) == "first"
    with pytest.raises(ValueError, match="upstream died"):
        next(gen)


def test_an_exception_raised_before_any_item_still_propagates():
    def boom():
        raise RuntimeError("no model configured")
        yield  # pragma: no cover - unreachable, makes this a generator

    with pytest.raises(RuntimeError, match="no model configured"):
        list(with_keepalive(boom(), _ping, interval=5.0))


def test_the_keepalive_factory_is_called_per_frame():
    """Frames must be independent objects — they are serialized one line at a time."""
    made: list[int] = []

    def counter():
        made.append(1)
        return {"n": len(made)}

    def slow():
        time.sleep(0.22)
        yield "done"

    out = list(with_keepalive(slow(), counter, interval=0.05))
    pings = [x for x in out if x != "done"]
    assert [p["n"] for p in pings] == list(range(1, len(pings) + 1))

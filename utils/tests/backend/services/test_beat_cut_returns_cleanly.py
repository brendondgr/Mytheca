"""A beat that is CUT must return, not raise.

`raw` was assigned only in `stream_emission`'s `StopIteration` handler, so every path that
broke out of the streaming loop early left it unbound and the turn died with
`UnboundLocalError: cannot access local variable 'raw'`. Two paths break that way — the
cross-speaker cut and the interiority cut — and both are guards whose whole job is to salvage
a beat rather than lose the turn.

It surfaced as "The turn failed unexpectedly" in a live run, which is the least useful
possible description of a guard working correctly and then crashing on the way out.
"""

from __future__ import annotations

import inspect

from app.services import beat_stream


def test_every_streaming_exit_defines_what_it_returns():
    """Structural, deliberately.

    Reproducing a mid-stream cut through the API needs a model that leaks on cue; asserting
    that the variable is bound BEFORE the try is what actually prevents the class of bug,
    and it cannot pass by accident.
    """
    for name in ("stream_emission", "stream_script"):
        src = inspect.getsource(getattr(beat_stream, name))
        body = src[: src.index("    try:")]
        assert 'raw, prompt_tokens = "", None' in body, (
            f"{name} must define `raw` before the loop it can break out of"
        )


def test_the_cut_guards_still_break_out():
    """The initialisation is only load-bearing while these paths exist."""
    src = inspect.getsource(beat_stream.stream_emission)
    assert "cross_speaker_speech_span" in src
    assert "narrates_another_mind_span" in src

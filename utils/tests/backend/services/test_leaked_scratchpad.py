"""A thinking block that closes without opening.

Some serving stacks have the chat template consume the opening ``<think>`` and hand back only
the closing tag, so the model's deliberation arrives on the ordinary content channel looking
exactly like prose — until the moment it ends. Measured live: a narrator beat streamed the
model's own checklist ("Never speak for a character or write dialogue: no dialogue. Good.")
into the scene, and the point-of-view guards then flagged the CHECKLIST for saying "the
player", which is a confusing way to be told your scratchpad is in the story.

`InlineReasoningSplitter` handled the matched form and passed this one straight through,
because it never saw an opening tag to switch on.
"""

from __future__ import annotations

import pytest

from app.agents._common import InlineReasoningSplitter


def test_the_matched_form_still_works():
    s = InlineReasoningSplitter()
    answer, reasoning = s.push("Before.<think>hidden</think>After.")
    assert answer == "Before.After."
    assert reasoning == "hidden"
    assert s.took_over() is False


def test_an_unopened_close_reclassifies_everything_before_it():
    s = InlineReasoningSplitter()
    first, _ = s.push("Checklist: no dialogue. Good. ")
    assert first == "Checklist: no dialogue. Good. ", "it looks like prose until the tag lands"
    assert s.took_over() is False

    answer, reasoning = s.push("Going with this.</think>The lamp gutters.")
    assert answer == "The lamp gutters."
    assert reasoning == "Going with this."
    assert s.took_over() is True, "the consumer must be told to discard what it showed"


def test_it_fires_at_most_once_per_generation():
    """A model that emits several close tags must not keep discarding its own prose.

    Otherwise a passage containing the literal string in dialogue — or a second stray tag —
    would throw away everything written since the first one.
    """
    s = InlineReasoningSplitter()
    s.push("thinking</think>Real prose begins. ")
    assert s.took_over() is True
    answer, _ = s.push("More prose</think>and more.")
    assert s.took_over() is False
    assert "More prose" in answer


def test_a_stream_with_no_tags_is_untouched():
    s = InlineReasoningSplitter()
    answer, reasoning = s.push("Just prose, all the way down.")
    assert answer == "Just prose, all the way down."
    assert reasoning == ""
    assert s.took_over() is False


@pytest.mark.parametrize("split_at", [3, 10, 22])
def test_a_tag_split_across_deltas_still_resolves(split_at):
    """The tag arrives in pieces on a real stream; a partial one must not reach the story."""
    whole = "deliberation here</think>The prose."
    s = InlineReasoningSplitter()
    got = ""
    for chunk in (whole[:split_at], whole[split_at:]):
        answer, _ = s.push(chunk)
        if s.took_over():
            got = ""  # the consumer discards what it had
        got += answer
    got += s.flush()[0]
    assert got == "The prose."

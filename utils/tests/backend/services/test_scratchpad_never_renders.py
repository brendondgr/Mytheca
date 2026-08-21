"""A passage that is the model briefing itself never reaches the reader.

Two beats in live session ``ps_0f0d1a6900`` were persisted and rendered as a character's
prose while being nothing of the kind:

* ``seq=16`` — the output contract read back to itself: *"then main passage then optional
  structured blocks each opening tag own line JSON below NO closing tag per instructions…"*
* ``seq=14`` — third-person planning about the character the model was supposed to BE:
  *"Kira's condition right now — …; must carry that into response to what just happened
  (… player named drowned ledger). Beat direct…"*

Both are well-formed language, so ``looks_degenerate`` passes them. The rule is a
conjunction on the opening — production vocabulary AND no first-person pronoun — because a
real passage starts in the scene on its first word.
"""

from __future__ import annotations

from app.services.emission import in_the_scene, looks_like_scratchpad

CONTRACT_LEAK = (
    "then main passage then optional structured blocks each opening tag own line JSON "
    "below NO closing tag per instructions AFTER passage may append structured block each "
    "own opening tag line JSON object beneath NO closing tag yes follow precisely ensure "
    "main answer contains ONLY tagged format meaning thinking tags + prose + blocks"
)
PLANNING_LEAK = (
    "Kira’s condition right now — steadier since the question got shape but old "
    "watch-caution coiled under it; wants which door each man used and whether both "
    "entries same hand; can no longer pretend either is merely passing — must carry that "
    "into response to what just happened (Aldous uncrossed/stepped closer watching her; "
    "player named drowned ledger; Mei’s fence/splinter speech trailing). Beat direct"
)
GOOD = (
    "The salt. The word hits me before the sentence finishes, cold and crystalline, "
    "settling into the hollow of my chest where I have been keeping it for three weeks. "
    "I do not look at Aldous, nor at the drowned ledger lying open on the scarred wood."
)


def test_the_contract_read_back_is_caught():
    assert looks_like_scratchpad(CONTRACT_LEAK) is True


def test_third_person_planning_about_the_character_is_caught():
    assert looks_like_scratchpad(PLANNING_LEAK) is True


def test_real_prose_is_not_caught():
    assert looks_like_scratchpad(GOOD) is False


def test_a_character_may_say_the_production_words():
    """The vocabulary alone would be far too eager — the pronoun rule is what saves it."""
    text = (
        "My heart beat is loud in the passage behind the kitchen, and I press my back to "
        "the block of stone until it slows. The format of this place is a trap and I know it."
    )
    assert looks_like_scratchpad(text) is False


def test_a_name_ending_in_i_is_not_a_first_person_pronoun():
    """"Mei's" once matched a substring test for ``i'`` and exempted a real leak."""
    assert in_the_scene("Mei’s fence and Kiri's ledger") is False
    assert in_the_scene("I’m late") is True
    assert in_the_scene("Aldous waits. I do not.") is True


def test_scene_prose_without_the_vocabulary_is_never_caught():
    """Third-person-ish opening lines are a style, not a leak."""
    text = (
        "Rain. Three days of it, and the road out of the valley is gone under brown "
        "water. The horses will not cross. Aldous knows it and says nothing, which is "
        "his way of saying a great deal to anyone still listening at this hour."
    )
    assert looks_like_scratchpad(text) is False


def test_an_empty_passage_is_not_a_leak():
    assert looks_like_scratchpad("") is False
    assert looks_like_scratchpad("   \n ") is False


def test_a_passage_that_opens_lowercase_never_started():
    """Observed live: a 62-character fragment of the model's own notes reached the page.

    ``looks_like_scratchpad`` cannot see it — it contains "my", so the first-person test
    exempts it, and its vocabulary is ordinary. What gives it away is that it begins in the
    middle of a sentence.
    """
    from app.services.emission import starts_mid_sentence

    assert starts_mid_sentence("flat composure build in my own voice rather than restating it.")
    assert starts_mid_sentence("and then the door") is True


def test_an_ordinary_opening_is_not_a_fragment():
    from app.services.emission import starts_mid_sentence

    assert starts_mid_sentence(GOOD) is False
    assert starts_mid_sentence('"You already knew," I say.') is False  # opens on a quote
    assert starts_mid_sentence("— and there it is.") is False  # opens on a dash
    assert starts_mid_sentence("...I let it sit.") is False  # opens on an ellipsis
    assert starts_mid_sentence("") is False

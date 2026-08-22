"""The lexical check that decides whether a beat's prose reached what was asked for.

Crude on purpose: it runs after every beat on the turn's hot path, so an accurate signal
costing an LLM round-trip per beat is not affordable. What matters is that its errors fall
the safe way — a false negative costs one more attempt, while a false positive silently
drops what the player asked for. These cases pin the arithmetic and the one rule that stops
it being systematically biased against in-voice delivery.
"""

from __future__ import annotations

from app.services import direction_check as dc


def test_content_words_drops_stopwords_and_short_tokens():
    words = dc.content_words("The lamp goes over and it is on the floor")
    assert "lamp" in words
    assert "floor" in words
    # "the", "and", "is", "on", "it", "over", "goes" carry no evidence either way.
    assert "the" not in words and "and" not in words


def test_content_words_stems_by_prefix():
    # `storms` / `stormed` / `storming` must all match `storm`.
    assert dc.content_words("storms") == dc.content_words("stormed") == dc.content_words("storming")


def test_full_coverage_is_one():
    assert dc.coverage("the lamp goes over", "The lamp goes over with a crash.") == 1.0


def test_no_coverage_is_zero():
    assert dc.coverage("the lamp goes over", "They talk quietly about the weather.") == 0.0


def test_partial_coverage_is_the_fraction_of_content_words():
    # wanted = {lamp, goes→goes is a stopword…} — assert on a stable pair instead.
    score = dc.coverage("Mei storms out and slams the door", "She slams the door behind her.")
    assert 0.0 < score < 1.0


def test_an_empty_requirement_covers_nothing():
    # Nothing was asked for, so nothing is covered — a caller must NOT read this as
    # "delivered", which is why it returns 0.0 rather than 1.0.
    assert dc.coverage("", "anything at all") == 0.0
    assert dc.coverage("   ", "anything at all") == 0.0


def test_the_bound_actors_name_is_not_held_against_them():
    """A requirement reads "Mei snaps back"; Mei's own in-voice beat never says "Mei".

    Without this rule the check would be biased against exactly the beats it most wants to
    confirm — every requirement delivered in the character's own voice would under-score.
    """
    req, beat = "Mei snaps back", '"Don\'t," she snaps back at him.'
    assert dc.coverage(req, beat) < 1.0
    assert dc.coverage(req, beat, ignore_names=["Mei"]) == 1.0


def test_ignoring_a_name_that_is_the_whole_requirement_covers_nothing():
    # Guard against the empty-set division: stripping the name can empty the word set.
    assert dc.coverage("Mei", "she says something", ignore_names=["Mei"]) == 0.0


def test_reached_is_the_threshold_boundary():
    req, beat = "Mei storms out and slams the door", "She storms out."
    score = dc.coverage(req, beat, ignore_names=["Mei"])
    assert dc.reached(req, beat, threshold=score, ignore_names=["Mei"]) is True
    assert dc.reached(req, beat, threshold=score + 0.01, ignore_names=["Mei"]) is False


def test_empty_prose_never_reaches_anything():
    # The common case in practice: a beat that came back with nothing at all.
    assert dc.reached("the lamp goes over", "", threshold=0.5) is False


# ---- calibration: what real prose actually looks like ------------------------


LIVE_BEAT = (
    "Nyssa's fingers tighten around the rim of her pewter cup, her knuckles turning a pale, "
    "waxy white against the salt-stained table. The rhythmic drip of water from the ceiling "
    "suddenly feels like a hammer against your nerves as she snaps, her hand sweeping "
    "outward in a sharp, jagged arc. The cup clatters across the stone floor, spilling its "
    "dark contents to seep into the white salt rings."
)


def test_an_abstract_subject_placeholder_is_not_held_against_the_prose():
    """"a character loses their temper" means *anyone*.

    No prose will ever contain the word "character", because prose names people. Left in the
    word set it is a guaranteed miss on a whole class of word — a fixed penalty applied to
    exactly the requirements phrased most generally, which is the opposite of a signal.
    """
    assert "chara" not in dc.content_words("a character loses their temper")
    assert "someo" not in dc.content_words("someone slams the door")


def test_the_live_case_that_was_retried_twice_now_confirms():
    """A regression test taken from a real turn, not an invented one.

    The engine asked for "a character loses their temper and knocks a cup off the table". The
    narrator wrote the beat below — which plainly does it — and the check scored it 0.33 and
    retried a direction the scene had already carried out, twice, burning half the scene's
    beat budget.

    Two things were wrong, and both are about how prose works rather than about this one
    sample: the placeholder "character" can never appear, and good writing paraphrases a
    requirement's VERBS ("loses their temper" -> "she snaps", "knocks ... off" -> "clatters
    across the floor") while keeping its concrete NOUNS. Demanding half the words demands
    that the paraphrase not happen.
    """
    req = "a character loses their temper and knocks a cup off the table"
    assert dc.reached(req, LIVE_BEAT, threshold=0.34) is True
    # …and it was genuinely below the old bar, which is why this is worth pinning.
    assert dc.reached(req, LIVE_BEAT, threshold=0.5) is False


def test_prose_about_something_else_still_fails_at_the_lower_bar():
    """Lowering the bar must not make the check meaningless."""
    req = "a character loses their temper and knocks a cup off the table"
    unrelated = "They speak quietly about the tide, and the lamplight holds steady."
    assert dc.reached(req, unrelated, threshold=0.34) is False


WREN_BEAT = (
    "The scent hits me hard, sharp as a gut-knife. Nyssa's looking right through me. "
    '"Aye, the ledger\'s a sham," I spit, the words tasting like copper in my mouth. '
    '"Every line, every number - it\'s all just ink and a bit of cleverness." '
    'I wipe a palm against my trousers. "I did the work, Nyssa. Just me and a steady hand."'
)


def test_a_speech_act_verb_is_not_held_against_the_line_that_performs_it():
    """"Wren admits the ledger was forged" describes what a line *does*; the line performs it.

    Nobody writes "I admit" — they write "Aye, the ledger's a sham." Naming the act from
    outside means the word can only ever be absent from the act itself, so counting it is a
    guaranteed miss on every requirement phrased the way people actually phrase them.
    """
    assert "admit" not in dc.content_words("Wren admits the ledger was forged")
    assert "revea" not in dc.content_words("she reveals the truth")
    assert "refus" not in dc.content_words("he refuses to answer")


def test_the_second_live_case_now_confirms():
    """A regression test from a real turn. Wren plainly confessed, and the check scored it
    0.33 — one hundredth under the bar — then retried twice and carried the requirement over
    as undelivered. The cause was "admits", not the writing."""
    req = "Wren Calloway admits the ledger was forged"
    assert dc.reached(req, WREN_BEAT, threshold=0.34, ignore_names=["Wren Calloway"]) is True


def test_a_beat_that_dodges_the_confession_still_fails():
    """Stopwording the verb must not make the requirement unfalsifiable — the OBJECT of the
    speech act ("the ledger", "forged") is what carries the evidence, and it is still
    required."""
    req = "Wren Calloway admits the ledger was forged"
    dodge = '"I have nothing to say to you," I mutter, and turn back to the window.'
    assert dc.reached(req, dodge, threshold=0.34, ignore_names=["Wren Calloway"]) is False


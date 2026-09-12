"""Thin-tag emission parser: speaker resolution, type segments, thinking, fallbacks."""

from __future__ import annotations

from app.services.emission import parse_emission


def test_parses_speaker_action_and_dialogue():
    raw = (
        "<speaker:2>\n"
        "<type:character_action>\nKira's jaw tightens.\n"
        "<type:character_dialogue>\n\"I was on watch.\""
    )
    segs = parse_emission(raw, roster={1: "mei", 2: "kira"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["character_prose"]
    assert all(s.character_id == "kira" for s in segs)
    assert "Kira's jaw tightens." in segs[0].text
    assert '"I was on watch."' in segs[0].text


def test_thinking_block_becomes_hidden_internal_thought_first():
    raw = (
        "<speaker:1>\n<thinking>Coin first, favor later. Let him sweat.</thinking>\n"
        "<type:character_dialogue>\n\"Coin's easy.\""
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert segs[0].type == "internal_thought" and segs[0].text == "Coin first, favor later. Let him sweat."
    assert segs[1].type == "character_prose" and segs[1].text == '"Coin\'s easy."'


def test_action_only_beat_has_no_forced_dialogue():
    # An action moment: the character acts (and thinks) with NO spoken line — the parser
    # emits exactly those segments, never a synthesized dialogue line.
    raw = (
        "<speaker:1>\n<thinking>No time to talk — move.</thinking>\n"
        "<type:character_action>\nducks the swing, grabs the bat"
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["internal_thought", "character_prose"]
    assert segs[1].text  # the beat is a passage, action and all


def test_thinking_only_beat_emits_only_the_hidden_thought():
    # A silent beat: only interiority, no visible action or dialogue.
    raw = "<speaker:1>\n<thinking>She's lying. I hold my tongue and watch.</thinking>"
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["internal_thought"]


def test_out_of_roster_speaker_falls_back_to_intended():
    segs = parse_emission(
        "<speaker:9>\n<type:character_dialogue>\nHi.", roster={1: "mei"}, fallback_speaker_id="mei"
    )
    assert segs[0].character_id == "mei"


def test_untagged_reply_becomes_one_prose_passage():
    """The expected shape: no tags at all, one first-person passage."""
    raw = 'I do not move. The rain finds my collar. "Say it again," I tell him.'
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert len(segs) == 1
    assert segs[0].type == "character_prose" and segs[0].text == raw


def test_prose_before_a_json_tag_is_kept_as_the_beat():
    """Plain prose followed by a JSON trailer — the one hybrid the contract allows."""
    raw = (
        'I set the cup down. "Then we are done here."\n'
        '<type:state_update>\n{"key": "trust", "delta": -2, "reason": "he lied"}'
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["character_prose", "state_update"]
    assert segs[0].text.startswith("I set the cup down.")


def test_empty_type_body_is_dropped():
    raw = "<speaker:1>\n<type:character_action>\n\n<type:character_dialogue>\n\"Hi.\""
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["character_prose"]


def test_no_speaker_tag_uses_fallback():
    segs = parse_emission(
        "<type:character_dialogue>\nHi there.", roster={1: "mei"}, fallback_speaker_id="mei"
    )
    assert segs[0].character_id == "mei" and segs[0].text == "Hi there."


# ---- tolerance for closing-style / XML-style tags (bug: leaked </type:…> + no bubble) --


def test_closing_style_tags_are_delimiters_not_text():
    # Some models emit </type:next> as the delimiter; it must split cleanly, not leak.
    raw = (
        "<speaker:1>\n"
        "<type:character_action> Sylvarra glides forward, tracing Luna's jaw. </type:character_dialogue> "
        "Then bloom for me, my precious thing. </type:character_action>"
    )
    segs = parse_emission(raw, roster={1: "syl"}, fallback_speaker_id="syl")
    assert [s.type for s in segs] == ["character_prose"]
    assert "Sylvarra glides forward, tracing Luna's jaw." in segs[0].text
    assert "Then bloom for me, my precious thing." in segs[0].text
    assert all("type:" not in s.text and "<" not in s.text for s in segs)


def test_paired_xml_style_collapses_to_one_segment():
    raw = "<speaker:1>\n<type:character_dialogue>Hello there.</type:character_dialogue>"
    segs = parse_emission(raw, roster={1: "a"}, fallback_speaker_id="a")
    assert [s.type for s in segs] == ["character_prose"]
    assert segs[0].text == "Hello there."


def test_state_update_via_closing_delimiter_parses_json_no_leak():
    raw = (
        "<speaker:1>\n"
        "<type:character_dialogue> Bloom for me. </type:state_update> "
        '{"key": "sensation", "delta": 10, "reason": "the grove"}'
    )
    segs = parse_emission(raw, roster={1: "syl"}, fallback_speaker_id="syl")
    assert [s.type for s in segs] == ["character_prose", "state_update"]
    assert segs[0].text == "Bloom for me."  # dialogue clean (no </type:…> leaked)
    assert "sensation" in segs[1].text and segs[1].text.strip().startswith("{")  # raw JSON kept


def test_relationship_update_block_kept_as_json():
    raw = (
        "<speaker:1>\n"
        '<type:character_dialogue>\n"Fine."\n'
        '<type:relationship_update>\n{"target": "Beth", "type": "resents", "reason": "she lied"}'
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["character_prose", "relationship_update"]
    assert segs[1].text.strip().startswith("{") and "resents" in segs[1].text  # raw JSON kept


def test_presence_change_block_kept_as_json():
    raw = (
        "<speaker:1>\n"
        '<type:character_action>\nturns and walks out\n'
        '<type:presence_change>\n{"status": "left", "reason": "done arguing"}'
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["character_prose", "presence_change"]
    assert segs[1].text.strip().startswith("{") and "left" in segs[1].text  # raw JSON kept


def test_bare_closing_type_tag_is_scrubbed_not_leaked():
    # Some models append a bare </type> (no name) at the end of each block; it must be
    # scrubbed from the visible prose, not rendered (the reported "</type>" leak).
    raw = (
        "<speaker:1>\n"
        "<type:character_action>\nsteps forward, chest heaving </type>\n"
        '<type:character_dialogue>\n"I don\'t break, I get more dangerous." </type>'
    )
    segs = parse_emission(raw, roster={1: "kaia"}, fallback_speaker_id="kaia")
    assert [s.type for s in segs] == ["character_prose"]
    assert "steps forward, chest heaving" in segs[0].text
    assert '"I don\'t break, I get more dangerous."' in segs[0].text
    assert all("</type>" not in s.text and "<" not in s.text for s in segs)


def test_bare_closing_tag_inside_thinking_is_scrubbed():
    raw = (
        "<speaker:1>\n<thinking>Let's see if he can handle the heat. </type></thinking>\n"
        '<type:character_dialogue>\n"Do something about it."'
    )
    segs = parse_emission(raw, roster={1: "kaia"}, fallback_speaker_id="kaia")
    assert segs[0].type == "internal_thought"
    assert segs[0].text == "Let's see if he can handle the heat."
    assert "</type>" not in segs[0].text


def test_reported_sylvarra_beat_parses_clean():
    raw = (
        "<speaker:2>\n"
        "<type:character_action> Sylvarra glides forward, her movements serpentine. "
        "</type:character_dialogue> Then bloom for me, my precious thing... "
        '</type:state_update> {"key": "sensation", "delta": 10, "reason": "the forest embrace"}'
    )
    segs = parse_emission(raw, roster={1: "luna", 2: "syl"}, fallback_speaker_id="syl")
    assert [s.type for s in segs] == ["character_prose", "state_update"]
    # No emission tags or raw JSON braces leak into the visible passage. Only the passage
    # is checked — the state_update segment IS raw JSON by design.
    assert "type:" not in segs[0].text and "{" not in segs[0].text
    assert all(s.character_id == "syl" for s in segs)


# ---- untagged JSON blocks ---------------------------------------------------
# The contract asks for `<type:state_update>` before a proposed change. Models write the
# object and skip the tag, which used to render the JSON verbatim under the beat AND drop
# the change it proposed.


def _parse(raw: str):
    return parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")


def test_untagged_stat_block_is_lifted_out_of_the_prose():
    segs = _parse('She turns the page.\n\n{"key": "patience", "delta": -1, "reason": "pressed"}')

    assert [s.type for s in segs] == ["character_prose", "state_update"]
    assert segs[0].text == "She turns the page."
    assert "delta" not in segs[0].text
    assert segs[1].text == '{"key": "patience", "delta": -1, "reason": "pressed"}'


def test_several_untagged_blocks_all_come_out():
    segs = _parse(
        'She turns the page.\n\n'
        '{"key": "patience", "delta": -1, "reason": "a"}\n\n'
        '{"key": "suspicion", "delta": 1, "reason": "b"}'
    )
    assert [s.type for s in segs] == ["character_prose", "state_update", "state_update"]


def test_untagged_blocks_are_typed_by_their_shape():
    rel = _parse('He steps back.\n\n{"type": "fears", "target": "Mei", "reason": "the ledger"}')
    pres = _parse('He walks out.\n\n{"status": "left", "reason": "done here"}')
    assert rel[-1].type == "relationship_update"
    assert pres[-1].type == "presence_change"


def test_prose_that_merely_contains_a_brace_is_untouched():
    segs = _parse("She writes {} on the slate and laughs.")
    assert [s.type for s in segs] == ["character_prose"]
    assert segs[0].text == "She writes {} on the slate and laughs."


def test_an_unrecognised_trailing_object_stays_prose():
    """A brace that does not match a validator's shape never cuts the passage."""
    segs = _parse('She turns the page.\n\n{"mood": "wary"}')
    assert [s.type for s in segs] == ["character_prose"]
    assert '{"mood": "wary"}' in segs[0].text


def test_text_after_an_untagged_block_is_trailing_and_dropped():
    """Matches the tagged path: prose after a JSON body is not a second passage."""
    segs = _parse('She turns the page.\n\n{"key": "trust", "delta": 1}\n\nAnd then she left.')
    assert [s.type for s in segs] == ["character_prose", "state_update"]
    assert segs[0].text == "She turns the page."
    assert "And then she left." not in segs[0].text


def test_an_unparseable_trailing_brace_stays_prose():
    segs = _parse("She turns the page.\n\n{key: patience, delta:")
    assert [s.type for s in segs] == ["character_prose"]


def test_a_tagged_block_still_wins():
    """The documented form is unaffected — it never reaches the bare-JSON path."""
    segs = _parse('She turns the page.\n<type:state_update>\n{"key": "trust", "delta": 1}')
    assert [s.type for s in segs] == ["character_prose", "state_update"]

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
    assert [s.type for s in segs] == ["character_action", "character_dialogue"]
    assert all(s.character_id == "kira" for s in segs)
    assert segs[0].text == "Kira's jaw tightens."
    assert segs[1].text == '"I was on watch."'


def test_thinking_block_becomes_hidden_internal_thought_first():
    raw = (
        "<speaker:1>\n<thinking>Coin first, favor later. Let him sweat.</thinking>\n"
        "<type:character_dialogue>\n\"Coin's easy.\""
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert segs[0].type == "internal_thought" and segs[0].text == "Coin first, favor later. Let him sweat."
    assert segs[1].type == "character_dialogue" and segs[1].text == '"Coin\'s easy."'


def test_action_only_beat_has_no_forced_dialogue():
    # An action moment: the character acts (and thinks) with NO spoken line — the parser
    # emits exactly those segments, never a synthesized dialogue line.
    raw = (
        "<speaker:1>\n<thinking>No time to talk — move.</thinking>\n"
        "<type:character_action>\nducks the swing, grabs the bat"
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["internal_thought", "character_action"]
    assert not any(s.type == "character_dialogue" for s in segs)


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


def test_untagged_reply_becomes_one_dialogue_line():
    segs = parse_emission("Just some prose, no tags.", roster={1: "mei"}, fallback_speaker_id="mei")
    assert len(segs) == 1
    assert segs[0].type == "character_dialogue" and segs[0].text == "Just some prose, no tags."


def test_empty_type_body_is_dropped():
    raw = "<speaker:1>\n<type:character_action>\n\n<type:character_dialogue>\n\"Hi.\""
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["character_dialogue"]


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
    assert [s.type for s in segs] == ["character_action", "character_dialogue"]
    assert segs[0].text == "Sylvarra glides forward, tracing Luna's jaw."
    assert segs[1].text == "Then bloom for me, my precious thing."
    assert all("type:" not in s.text and "<" not in s.text for s in segs)


def test_paired_xml_style_collapses_to_one_segment():
    raw = "<speaker:1>\n<type:character_dialogue>Hello there.</type:character_dialogue>"
    segs = parse_emission(raw, roster={1: "a"}, fallback_speaker_id="a")
    assert [s.type for s in segs] == ["character_dialogue"]
    assert segs[0].text == "Hello there."


def test_state_update_via_closing_delimiter_parses_json_no_leak():
    raw = (
        "<speaker:1>\n"
        "<type:character_dialogue> Bloom for me. </type:state_update> "
        '{"key": "sensation", "delta": 10, "reason": "the grove"}'
    )
    segs = parse_emission(raw, roster={1: "syl"}, fallback_speaker_id="syl")
    assert [s.type for s in segs] == ["character_dialogue", "state_update"]
    assert segs[0].text == "Bloom for me."  # dialogue clean (no </type:…> leaked)
    assert "sensation" in segs[1].text and segs[1].text.strip().startswith("{")  # raw JSON kept


def test_relationship_update_block_kept_as_json():
    raw = (
        "<speaker:1>\n"
        '<type:character_dialogue>\n"Fine."\n'
        '<type:relationship_update>\n{"target": "Beth", "type": "resents", "reason": "she lied"}'
    )
    segs = parse_emission(raw, roster={1: "mei"}, fallback_speaker_id="mei")
    assert [s.type for s in segs] == ["character_dialogue", "relationship_update"]
    assert segs[1].text.strip().startswith("{") and "resents" in segs[1].text  # raw JSON kept


def test_bare_closing_type_tag_is_scrubbed_not_leaked():
    # Some models append a bare </type> (no name) at the end of each block; it must be
    # scrubbed from the visible prose, not rendered (the reported "</type>" leak).
    raw = (
        "<speaker:1>\n"
        "<type:character_action>\nsteps forward, chest heaving </type>\n"
        '<type:character_dialogue>\n"I don\'t break, I get more dangerous." </type>'
    )
    segs = parse_emission(raw, roster={1: "kaia"}, fallback_speaker_id="kaia")
    assert [s.type for s in segs] == ["character_action", "character_dialogue"]
    assert segs[0].text == "steps forward, chest heaving"
    assert segs[1].text == '"I don\'t break, I get more dangerous."'
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
    assert [s.type for s in segs] == ["character_action", "character_dialogue", "state_update"]
    # No emission tags or raw JSON braces leak into the visible prose.
    for s in segs[:2]:
        assert "type:" not in s.text and "{" not in s.text
        assert s.character_id == "syl"

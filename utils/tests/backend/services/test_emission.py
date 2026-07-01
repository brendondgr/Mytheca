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

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

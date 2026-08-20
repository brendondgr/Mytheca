"""Band-1 context assembly: cast/setting/stats/guidance/buffer/subgraph + stable prefix."""

from __future__ import annotations

from app.core.config import get_settings
from app.memory import buffer
from app.models import Character, Scenario, Setting, Storyline
from app.models.stat import CharacterStat, StatDefinition
from app.services import assembler, events_store, stat_guidance


def _world(db) -> None:
    db.add(
        Storyline(
            id="embergate",
            title="Embergate",
            genre="Maritime",
            world_primer="Embergate is a rain-soaked harbor city run by guild charters.",
        )
    )
    db.commit()
    db.add(
        StatDefinition(
            storyline_id="embergate",
            key="health",
            display_name="Health",
            min=0,
            max=100,
            default=100,
            guidance="stats/health.md",
        )
    )
    db.add(
        StatDefinition(
            storyline_id="embergate", key="trust", display_name="Trust", min=0, max=100, default=50
        )
    )
    db.commit()


def _char(db, cid: str, name: str) -> None:
    db.add(Character(id=cid, storyline_id="embergate", name=name))
    db.commit()


def _scenario(db, cast: list[str], setting_id: str = "") -> Scenario:
    sc = Scenario(storyline_id="embergate", title="Standoff", cast_ids=cast, setting_id=setting_id)
    db.add(sc)
    db.commit()
    return sc


def test_assembles_cast_setting_stats_guidance(db_session):
    stat_guidance._clear_cache()
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    db_session.add(CharacterStat(character_id="c_mei", key="health", value=80))
    db_session.add(
        Setting(id="s_hearth", storyline_id="embergate", name="The Smoldering Hearth", current_state="smoky")
    )
    db_session.commit()
    sc = _scenario(db_session, ["c_mei"], "s_hearth")
    session = events_store.create_session(db_session, sc.id)

    ctx = assembler.assemble_context(db_session, sc, session.id, directed_at="c_mei")

    assert [m.name for m in ctx.cast] == ["Mei"]
    mei = ctx.cast[0]
    assert mei.stats["health"] == 80  # explicit value
    assert mei.stats["trust"] == 50  # default filled for an unset stat
    assert ctx.setting is not None and ctx.setting.name == "The Smoldering Hearth"
    assert ctx.stat_guidance.get("health")  # loaded from content/stats/health.md
    assert "Embergate is a rain-soaked harbor city" in ctx.stable_prefix
    assert "Health" in ctx.stable_prefix  # stat guidance folded into the cacheable prefix
    assert ctx.directed_at == "c_mei"


def test_graph_down_yields_empty_subgraph(db_session):
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert ctx.subgraph["available"] is False
    assert ctx.subgraph["nodes"] == [] and ctx.subgraph["edges"] == []


def test_presence_defaults_present_then_reflects_status_events(db_session):
    from app.models import Event

    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    _char(db_session, "c_wren", "Wren")
    sc = _scenario(db_session, ["c_mei", "c_wren"])
    session = events_store.create_session(db_session, sc.id)

    # No status events yet → everyone present + selectable.
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert [m.presence for m in ctx.cast] == ["present", "present"]
    assert all(m.is_present for m in ctx.cast)

    # A status-change event on the log marks Mei dead; the fold stamps the cast.
    db_session.add(
        Event(
            type="character_status_change",
            seq=1,
            scenario_id=sc.id,
            session_id=session.id,
            data={"characterId": "c_mei", "status": "dead", "reason": "run through", "auto": True},
        )
    )
    db_session.commit()
    ctx = assembler.assemble_context(db_session, sc, session.id)
    mei = ctx.cast_by_id("c_mei")
    wren = ctx.cast_by_id("c_wren")
    assert mei is not None and mei.presence == "dead" and not mei.is_present
    assert wren is not None and wren.is_present


def test_dangling_cast_id_is_skipped(db_session):
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei", "c_ghost"])  # c_ghost was deleted
    session = events_store.create_session(db_session, sc.id)
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert [m.id for m in ctx.cast] == ["c_mei"]


def test_voice_samples_rendered_into_cast(db_session):
    _world(db_session)
    db_session.add(
        Character(
            id="c_mei",
            storyline_id="embergate",
            name="Mei",
            voice_samples=[
                {"situation": "haggling", "sample": "Coin first, favor later."},
                {"situation": "threatened", "sample": "Try it."},
            ],
        )
    )
    db_session.commit()
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    ctx = assembler.assemble_context(db_session, sc, session.id)
    block = ctx.cast[0].voice_samples
    assert "Coin first, favor later." in block
    assert 'Prompt: "haggling"' in block and 'Prompt: "threatened"' in block


def test_voice_samples_empty_when_unauthored(db_session):
    _world(db_session)
    _char(db_session, "c_mei", "Mei")  # no voice_samples
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert ctx.cast[0].voice_samples == ""


def test_in_voice_anchors_pulled_per_character(db_session, monkeypatch):
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    monkeypatch.setattr(
        buffer,
        "anchored_turns",
        lambda sid, window, block: [
            {"role": "player", "text": "I slide the pouch.", "characterId": None},
            {"role": "character", "text": "Coin's easy.", "characterId": "c_mei"},
            {"role": "character", "text": "Quiet's cheaper.", "characterId": "c_mei"},
            {"role": "character", "text": "Not your dock.", "characterId": "c_other"},
        ],
    )
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert ctx.cast[0].recent_lines == ["Coin's easy.", "Quiet's cheaper."]
    assert ctx.recent_beats[0]["text"] == "I slide the pouch."


def test_skip_turn_injects_no_lore(db_session):
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    ctx = assembler.assemble_context(db_session, sc, session.id, player_text="I sit down quietly.")
    assert ctx.retrieved_lore == ""
    assert ctx.gate_reason.startswith("skip")


def test_fetch_turn_injects_gated_lore(db_session, monkeypatch):
    from app.agents import _common

    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    monkeypatch.setattr(
        _common, "rag_block", lambda db, sid, q: "\n\nRETRIEVED LORE:\n- the Ashford fire."
    )
    ctx = assembler.assemble_context(
        db_session, sc, session.id, player_text="Tell me about the Ashford fire."
    )
    assert "Ashford fire" in ctx.retrieved_lore
    assert ctx.gate_reason.startswith("fetch")


def test_interior_disposition_read_into_cast(db_session, monkeypatch):
    from app.memory import interior as interior_mem
    from app.memory.interior import InteriorRecord

    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    monkeypatch.setattr(
        interior_mem,
        "get_interior",
        lambda sid, cid: (
            InteriorRecord(character_id=cid, disposition="Guarded and tired.")
            if cid == "c_mei"
            else None
        ),
    )
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert ctx.cast[0].disposition == "Guarded and tired."


def test_no_interior_leaves_disposition_empty(db_session):
    # Interior is disabled (no Redis) by the autouse fixture → clean empty disposition.
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    session = events_store.create_session(db_session, sc.id)
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert ctx.cast[0].disposition == ""


def test_no_stats_defined_is_clean(db_session):
    db_session.add(Storyline(id="bare", title="Bare", genre="X"))
    db_session.commit()
    db_session.add(Character(id="c_x", storyline_id="bare", name="X"))
    db_session.commit()
    sc = Scenario(storyline_id="bare", title="S", cast_ids=["c_x"], setting_id="")
    db_session.add(sc)
    db_session.commit()
    session = events_store.create_session(db_session, sc.id)
    ctx = assembler.assemble_context(db_session, sc, session.id)
    assert ctx.cast[0].stats == {}
    assert ctx.stat_guidance == {}
    assert ctx.setting is None


def test_context_beats_is_the_buffer_fetch_depth(db_session, monkeypatch):
    # The scene's context_beats drives how many recent beats are fetched and is exposed on
    # the TurnContext (the character transcript window reads it).
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    sc.context_beats = 40
    db_session.commit()
    captured: dict = {}

    def fake_anchored(session_id, window, block):
        captured.update({"window": window, "block": block})
        return []

    monkeypatch.setattr(assembler.buffer, "anchored_turns", fake_anchored)
    ctx = assembler.assemble_context(db_session, sc, "ps1")
    assert captured["window"] == 40
    assert captured["block"] == get_settings().turn_transcript_anchor_block
    assert ctx.context_beats == 40


def test_context_beats_out_of_range_is_clamped(db_session, monkeypatch):
    # A stored value beyond the 5–100 window is clamped defensively before use.
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    sc.context_beats = 500
    db_session.commit()
    monkeypatch.setattr(assembler.buffer, "anchored_turns", lambda session_id, window, block: [])
    ctx = assembler.assemble_context(db_session, sc, "ps1")
    assert ctx.context_beats == 100


# ---- Register-aware voice-sample selection ---------------------------------
# Injecting every at-rest sample on every beat is what made characters sound scripted:
# the concrete exemplars outweigh any abstract instruction to adapt. Selection narrows
# them to the moment, but must never leave a character with nothing.

_ROWS = [
    {"situation": "haggling", "sample": "Coin first.", "moment": "light"},
    {"situation": "a blade at his throat", "sample": "Wait—wait.", "moment": "grave"},
    {"situation": "anything at all", "sample": "Mm.", "moment": ""},
]


def test_selection_keeps_the_matching_and_untagged_samples():
    picked = assembler.select_voice_samples(_ROWS, "grave")
    assert [s["sample"] for s in picked] == ["Wait—wait.", "Mm."]


def test_selection_without_a_register_returns_everything():
    # No register (planner fallback / puppet beat) → byte-identical to pre-register behavior.
    assert assembler.select_voice_samples(_ROWS, None) == _ROWS


def test_selection_falls_back_to_all_when_nothing_matches():
    # A world authored before the field, or a register no pair demonstrates: the character
    # keeps its whole voice profile rather than losing it.
    untagged = [{"situation": "x", "sample": "y"}]
    assert assembler.select_voice_samples(untagged, "grave") == untagged
    only_light = [{"situation": "x", "sample": "y", "moment": "light"}]
    assert assembler.select_voice_samples(only_light, "grave") == only_light


def test_selection_tolerates_junk_rows():
    assert assembler.select_voice_samples(None, "tense") == []
    assert assembler.select_voice_samples(["not a dict", 7], "tense") == []

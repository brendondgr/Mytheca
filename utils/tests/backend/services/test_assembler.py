"""Band-1 context assembly: cast/setting/stats/guidance/buffer/subgraph + stable prefix."""

from __future__ import annotations

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
        "recent_turns",
        lambda sid, limit=None: [
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

    def fake_recent(session_id, limit=None):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(assembler.buffer, "recent_turns", fake_recent)
    ctx = assembler.assemble_context(db_session, sc, "ps1")
    assert captured["limit"] == 40
    assert ctx.context_beats == 40


def test_context_beats_out_of_range_is_clamped(db_session, monkeypatch):
    # A stored value beyond the 5–100 window is clamped defensively before use.
    _world(db_session)
    _char(db_session, "c_mei", "Mei")
    sc = _scenario(db_session, ["c_mei"])
    sc.context_beats = 500
    db_session.commit()
    monkeypatch.setattr(assembler.buffer, "recent_turns", lambda session_id, limit=None: [])
    ctx = assembler.assemble_context(db_session, sc, "ps1")
    assert ctx.context_beats == 100

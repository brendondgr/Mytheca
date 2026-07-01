"""Event envelope types + persistence (chat scaffold, data only)."""

from __future__ import annotations

from app.events import InternalThoughtEvent, StateUpdateEvent, story_event_adapter
from app.models import Event, PlaySession, Scenario, Storyline


def _envelope(type_: str, data: dict) -> dict:
    return {
        "id": "ev1",
        "seq": 1,
        "scenarioId": "embergate",
        "sessionId": "ps1",
        "ts": "2026-06-21T00:00:00Z",
        "type": type_,
        "data": data,
    }


def test_parses_all_five_types():
    payloads = {
        "narration": {"text": "Rain ticks on the shutters."},
        "character_dialogue": {"characterId": "maerin", "text": "You're late."},
        "character_action": {"characterId": "wren", "text": "leans in, low"},
        "state_update": {"stat": {"characterId": "maerin", "key": "health", "delta": -25, "value": 55, "reason": "beam"}},
        "branch_choices": {"choices": [{"label": "Run", "outcome": "escape"}]},
    }
    for type_, data in payloads.items():
        event = story_event_adapter.validate_python(_envelope(type_, data))
        assert event.type == type_


def test_envelope_round_trips_camel_case():
    event = story_event_adapter.validate_python(_envelope("narration", {"text": "hi"}))
    dumped = event.model_dump(by_alias=True)
    assert dumped["scenarioId"] == "embergate" and dumped["sessionId"] == "ps1"


def test_parses_internal_thought_hidden_by_default():
    event = story_event_adapter.validate_python(
        _envelope("internal_thought", {"characterId": "mei", "text": "Let him sweat."})
    )
    assert isinstance(event, InternalThoughtEvent)
    # internal_thought is conditioning-only — hidden unless the caller overrides.
    assert event.visibility == "hidden"
    assert event.data.character_id == "mei"


def test_branch_choice_has_no_check_field():
    event = story_event_adapter.validate_python(
        _envelope("branch_choices", {"choices": [{"label": "Run", "outcome": "escape", "check": "Athletics"}]})
    )
    option = event.data.choices[0]
    assert option.label == "Run" and option.outcome == "escape"
    assert not hasattr(option, "check")  # dice removed (D11)
    assert "check" not in event.model_dump(by_alias=True)["data"]["choices"][0]


def test_state_update_carries_stat_patch():
    event = story_event_adapter.validate_python(
        _envelope("state_update", {"stat": {"characterId": "maerin", "key": "health", "value": 55, "reason": "x"}})
    )
    assert isinstance(event, StateUpdateEvent)
    assert event.data.stat is not None
    assert event.data.stat.key == "health" and event.data.stat.value == 55


def test_event_and_session_persist(db_session):
    db_session.add(Storyline(id="embergate", title="Embergate"))
    db_session.commit()
    scenario = Scenario(storyline_id="embergate", title="The Embergate Conspiracy")
    db_session.add(scenario)
    db_session.commit()
    session = PlaySession(scenario_id=scenario.id)
    db_session.add(session)
    db_session.commit()

    event = Event(type="narration", seq=1, scenario_id=scenario.id, session_id=session.id, data={"text": "hi"})
    db_session.add(event)
    db_session.commit()

    stored = db_session.get(Event, event.id)
    assert stored.type == "narration"
    assert stored.data["text"] == "hi"
    assert stored.ts is not None

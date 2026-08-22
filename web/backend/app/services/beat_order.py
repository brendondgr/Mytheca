"""Who speaks next, without asking a model.

The turn loop normally calls ``planner_agent.plan_beats`` — a ReAct planner that reads the
moment, decides who is up, inserts narrator beats and reports how tense things are.
EXP-2026-08-005 measured it at 41 % of all turn time, and it is the single largest latency
lever a player has. This module is what runs when they pull it: a **deterministic beat
order**, no model call, no tokens.

It is deliberately not new code. ``planner_agent.scripted_beat`` has always decided the beat
when the endpoint was unconfigured or the planner call failed, so it is exercised on every
offline path and by a large part of the test suite; turning planning off chooses that
existing order on purpose rather than introducing a second one.

The one thing added on top is the **round-robin**. ``scripted_beat`` ends a freeform
mid-scene turn after a single responder — correct as a fallback, where the goal is not to
stall — but as a chosen mode it would collapse every message to one line. So when it says
``end`` while a present, non-POV character has not taken a beat this turn and the scene's
budget still has room, the next such character in cast order speaks instead.

What is lost is stated plainly here because the UI has to state it too:

* **No ``register``, no ``stakes``.** Both are ``None``/``""`` on this path. The character
  prompt's tail, the voice-sample selection and the sampler all fall back to their
  pre-register behaviour. That is the honest consequence of nobody reading the moment, not
  an omission to be filled in later with a guess.
* **No narrator beats between speakers.** Deciding that a scene needs setting is a judgement,
  and this module makes none.
* **No exits.** A character the story has written out stays in the rotation until the player
  removes them from the cast rail.

Everything the *engine* enforces still applies — the exchange guard, the forced direction
schedule, the POV lockout, the silent-turn backstop, the runaway backstop and the hard
``max_turns`` cap — because those are the engine's rules, not the planner's.
"""

from __future__ import annotations

from app.agents.direction_agent import SceneDirection
from app.agents.intent_agent import TurnIntent
from app.agents.planner_agent import BeatDecision, scripted_beat
from app.services.assembler import TurnContext


def next_beat(
    ctx: TurnContext,
    intent: TurnIntent,
    acted: list[str],
    *,
    scene_opening: bool = False,
    locked_id: str | None = None,
    direction: SceneDirection | None = None,
    beats_left: int = 0,
) -> BeatDecision:
    """The next beat with planning off. Never raises, never calls a model.

    ``beats_left`` is the scene's remaining budget. The round-robin only extends a turn that
    still has room — the cap is the engine's and this must not argue with it.
    """
    decision = scripted_beat(
        ctx,
        intent,
        acted,
        scene_opening=scene_opening,
        locked_id=locked_id,
        direction=direction,
    )
    if decision.action != "end" or beats_left <= 0:
        return decision

    # A cold scene open with nothing asked for is narrator-led and ends here on purpose: the
    # narrator sets the moment (the engine does that) and the cast answers the player's NEXT
    # message. Forcing a speaker would have characters talking into an empty room.
    if scene_opening:
        return decision

    acted_set = {cid for cid in acted if cid != locked_id}
    for member in ctx.cast:
        if not member.is_present or member.id == locked_id:
            continue
        if member.id in acted_set:
            continue
        return BeatDecision(
            "speak", actor_id=member.id, reason="next in the cast, planning off"
        )
    return decision

"""Writing one free-text turn: the whole room, in one continuous passage.

The structured engine's writer voices exactly one character and the engine owns the envelope
around it. This one writes everybody — third person, dialogue in double quotes, no speaker
tags, no beat boundaries — and the engine's only job afterwards is to strip the consequence
blocks off the end.

Two things it does NOT carry, both deliberate and both the cost of one body:

* **A register.** The structured path pitches each beat light/neutral/tense/grave from the
  planner's read of the moment, and tunes ``top_p`` to match. A single passage spans several
  moments — that is the point of it — so pitching the whole thing at one register would be
  worse than pitching it at none. The sampler stays at the module baseline.
* **Per-character isolation.** Every voice sample is in one prompt (``freetext_context``),
  which will pull the cast together and will pull hardest on the weakest models. It is the
  trade the mode exists to make.

What it does carry that the other path cannot: it writes each part of the turn knowing what
the rest of it is.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.agents._common import gen_params, resolve_llm
from app.agents.character_turn_agent import _VOICE_TOP_P
from app.schemas.reasoning import ReasoningEffort, budget_for
from app.schemas.settings import LlmParams
from app.services import freetext_context, llm
from app.services.assembler import CastMember, TurnContext

logger = logging.getLogger("mytheca.turn")

#: Room for one passage, in tokens.
#:
#: **Not an editorial limit**, and much larger than the structured engine's per-beat
#: allowance (2048) because a free-text turn writes what that engine spreads over several
#: beats. The owner's requirement is that there is no limit on how much it can say.
#:
#: What it protects is the endpoint. The operator's global ``maxTokens`` is one number shared
#: with world-building, where a very long output is the point — 48,000 on this install — and
#: handing that to a turn is how one live generation ran to 48,000 completion tokens over 684
#: seconds, timed out the relay's health probe three times, left the upstream marked failed
#: and returned 400 for the next three turns. One generation cost the player the rest of
#: their scene.
#:
#: 6,000 tokens is roughly 24,000 characters — about eight times the longest honest beat ever
#: measured here (1,923 characters, EXP-2026-08-007) — so writing will not reach it. **This
#: number is chosen, not measured**, and it is the one figure in the mode the owner was asked
#: to set; see ``docs/plans/free-text-mode.md``.
PROSE_TOKENS = 6000

#: Hard stop on the streamed text, in characters, derived from the allowance above rather
#: than picked separately — two independently-chosen limits for one thing is how one of them
#: ends up wrong. ``max_tokens`` alone does not bound the prose, because thinking and answer
#: share it: a passage that deliberates briefly can spend the rest on writing.
RUNAWAY_CHARS = PROSE_TOKENS * 4

#: How much thinking a body gets when the player has not asked for a level.
#:
#: Unlike the structured engine's prose call — which runs at ``NONE`` because it executes a
#: decision the planner already made at a full budget — a free-text body IS the decision.
#: Nothing upstream chose who speaks, in what order, or where the passage lands, so it has to
#: work that out for itself. ``MEDIUM`` (512) is the plan's proposed default and the player
#: can move it in either direction from the composer.
DEFAULT_EFFORT = ReasoningEffort.MEDIUM

#: How much of the budget to leave the deliberation before it eats the passage. The endpoint
#: treats a thinking budget as a hint rather than a stop, so an overshoot can consume the room
#: the prose needed — which is how a beat once came back as reasoning with no answer.
_SCRATCHPAD_HEADROOM = 2


def params_for(params: LlmParams, effort: ReasoningEffort | None) -> LlmParams:
    """Bound one passage and apply the voice sampler.

    ``top_p`` only. The frequency and presence penalties stay at zero, and this must never be
    the place someone reintroduces them: EXP-2026-08-007 measured them destroying sentence
    structure in character prose (1.32 sentences per 100 words against 11.42 with them off,
    non-overlapping arms). They fall on the full stop, the comma and the quote mark, which is
    most of what prose is made of.
    """
    resolved = effort or DEFAULT_EFFORT
    # The passage allowance sits ON TOP of the thinking budget rather than sharing it: the
    # two come out of one ``max_tokens``, and setting them equal is how a generation spends
    # its whole budget deliberating and comes back as reasoning with no prose. The scratchpad
    # gets headroom because the endpoint treats a thinking budget as a hint, not a stop.
    allowance = PROSE_TOKENS + budget_for(resolved) * _SCRATCHPAD_HEADROOM
    # Against ``gen_params``'s floor, never the operator's raw ``max_tokens`` — that field
    # defaults to 512, which is a default rather than a choice and would truncate every
    # passage on a stock install.
    floored = gen_params(params)
    return floored.model_copy(
        update={
            "max_tokens": min(floored.max_tokens, allowance),
            "top_p": _VOICE_TOP_P,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }
    )


def stream_body(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    instruction: str,
    lore: str = "",
    pov: CastMember | None = None,
    extra: list[str] | None = None,
    effort: ReasoningEffort | None = None,
    usage_out: dict | None = None,
) -> Generator[llm.StreamDelta, None, tuple[str, int | None]]:
    """Stream one passage; return ``(text, prompt_tokens)``.

    ``instruction`` is what separates a first pass from a continuation — the prompt is
    otherwise identical, which is exactly why the continuation is cheap: it re-reads a prefix
    the first pass already warmed.
    """
    base_url, api_key, model, params = resolve_llm(db)
    messages = freetext_context.messages(
        ctx, turn_beats, instruction=instruction, lore=lore, pov=pov, extra=extra
    )
    return (
        yield from llm.chat_complete_stream(
            base_url, api_key, model, messages,
            params_for(params, effort),
            reasoning=effort or DEFAULT_EFFORT,
            usage_out=usage_out,
        )
    )


#: What the first pass is asked to do. Short on purpose: the contract in the system message
#: already says how a passage is written, and repeating it here would spend the recency
#: position restating what the model has already read.
WRITE = (
    "Write what happens next, as one continuous passage. Start in the scene, on your first "
    "word."
)


def continue_instruction(missing: list[str]) -> str:
    """What the turn is asked for when the review found something short.

    States the outcomes and forbids the two failure modes a continuation invites: starting
    again, and summarising what it already wrote. The passage on screen is not re-sent — it
    is already in the transcript block above, so re-sending it would double the scene in the
    prompt and invite the model to treat its own prose as something to paraphrase.
    """
    owed = "\n".join(f"- {text}" for text in missing)
    return (
        "That passage stopped before it finished. These are still not on the page:\n"
        f"{owed}\n\n"
        "Keep writing from exactly where it stopped — the next sentence of the same "
        "passage, not a new one. Do not restart, do not recap what has already been "
        "written, do not apologise or comment, and do not repeat any image or phrase from "
        "it. Reach the things above through what the characters actually do and say."
    )

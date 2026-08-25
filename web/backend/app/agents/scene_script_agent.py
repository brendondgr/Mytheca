"""Scene script agent — render a whole planned turn as ONE continuous passage.

This is the other half of `sceneFlow`. The shipped path (`"voiced"`) makes one model call per
speaker, carrying that character's voice samples, register and relationship note; this one
(`"continuous"`) makes a single call that writes every beat of the plan in order, marking each
change of speaker with ``<speaker:N>``.

**It reverses a deliberate decision, on the owner's judgement.** `character_turn_agent`'s
docstring says, in as many words: *"One LLM call per active speaker (per-character isolation —
no shared multi-POV prompt, so voices stay distinct)."* The owner's reason for overriding that
is that the isolation is not delivering — *"the characters aren't even abiding by their
ideological background, even with all of this being put into place"* — and the codebase has a
hint they are right: `beat_stream.echoes_a_beat` exists **because** two characters returned
byte-identical passages, and its own docstring blames "two separate calls whose prompts differ
only by a name and a role".

That is one anecdote, not a measurement, which is why this ships behind a toggle and why
`docs/checklist.md` names the experiment that would settle it.

What is genuinely bought and sold here, stated plainly:

* **Bought** — continuity (each beat is written knowing what the next one is, rather than
  inferring it from a transcript), attribution that comes from a token the writer emitted
  rather than from the engine guessing, and one call instead of N.
* **Sold** — per-character prompt isolation. Every voice sample in one prompt will pull the
  cast together, and it will pull hardest on exactly the weaker models this is supposed to be
  foolproof for.

**Degrades to the voiced path rather than to something worse.** A model too weak to emit the
speaker tokens produces one long passage attributed to the first speaker — which is not a
scene, it is a mis-attributed monologue. :func:`looks_unscripted` is what catches that, and
the caller falls back for that turn.
"""

from __future__ import annotations

import re
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import resolve_llm
from app.agents.character_turn_agent import _voice_params, prose_tokens_for
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import CastMember, TurnContext, format_voice_samples

#: Same budget as a character beat. A script writes several beats, so it needs several beats'
#: worth of room — the per-beat allowance is multiplied by the plan's length in
#: :func:`stream_script` rather than raised here, so a two-beat script cannot spend a
#: ten-beat script's tokens.
SCRIPT_EFFORT = ReasoningEffort.HIGH

_SPEAKER_TOKEN = re.compile(r"<speaker:\s*\d+\s*>", re.IGNORECASE)


def looks_unscripted(raw: str, *, expected_speakers: int) -> bool:
    """True when a script came back without the hand-offs that make it a script.

    A model that ignores the token format returns one long passage. Parsed, that becomes a
    single beat attributed to whoever was first — a mis-attributed monologue rather than a
    scene, and worse than what the voiced path would have produced.

    Deliberately lenient: only a script that was supposed to change speaker at all and
    contains **no** hand-off token counts. A script that emitted three of its four is still a
    scene, and re-running the whole turn to chase the fourth would cost more than it saves.
    """
    if expected_speakers < 2:
        return False
    return not _SPEAKER_TOKEN.search(raw or "")


def _roster_block(ctx: TurnContext, roster: dict[int, str]) -> str:
    """Who is on the roster, with the number the script marks their beats with."""
    lines = []
    for number, cid in roster.items():
        member = ctx.cast_by_id(cid)
        if member is None:
            continue
        lines.append(f"[{number}] {member.name} — {member.role}")
        if member.speech:
            lines.append(f"    Voice: {member.speech}")
        samples = format_voice_samples(member.voice_sample_rows) or member.voice_samples
        if samples:
            # Indented under their name so the block reads as one person's entry rather than
            # a wall of exemplars the model has to attribute for itself. This is the part
            # that is genuinely weaker than the voiced path, and it is where the cost of
            # continuous prose is paid.
            first = samples.strip().splitlines()[:2]
            lines.extend(f"    {line.strip()}" for line in first if line.strip())
    return "\n".join(lines)


def _plan_block(ctx: TurnContext, decisions) -> str:
    """The plan, as an ordered list of beats to write."""
    lines = []
    for i, d in enumerate(decisions, start=1):
        if d.action == "narrate":
            who = "NARRATOR"
        else:
            member = ctx.cast_by_id(d.actor_id) if d.actor_id else None
            who = member.name if member else "NARRATOR"
        bits = [f"{i}. {who}"]
        if d.reason:
            bits.append(f"— {d.reason}")
        if d.register:
            bits.append(f"[{d.register}]")
        if d.stakes:
            bits.append(f"(at stake: {d.stakes})")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def build_prompt(
    ctx: TurnContext,
    decisions,
    roster: dict[int, str],
    *,
    transcript: str,
    scene_direction: str,
    requirements: list[str] | None = None,
) -> tuple[str, str]:
    """The ``(system, user)`` pair for one script. Split out so it can be tested directly."""
    system = ctx.prompts.get(
        prompt_registry.SCENE_SCRIPT_SYSTEM,
        prompt_registry.default(prompt_registry.SCENE_SCRIPT_SYSTEM),
    )
    system = f"{system}\n\n{ctx.stable_prefix}".strip()

    numbers = {cid: n for n, cid in roster.items()}
    marks = []
    for d in decisions:
        number = numbers.get(d.actor_id or "")
        marks.append(f"<speaker:{number}>" if number else "<speaker:0>")

    owed = [r.strip() for r in (requirements or []) if r and r.strip()]
    owed_block = (
        "THIS TURN MUST MAKE ALL OF THIS TRUE: " + "; ".join(owed) + ".\n\n" if owed else ""
    )
    direction_block = f"The player's direction: {scene_direction}\n\n" if scene_direction else ""
    memory = (
        f"Earlier in this scene (summary):\n{ctx.history_summary}\n\n"
        if ctx.history_summary
        else ""
    )
    user = (
        f"Cast:\n{_roster_block(ctx, roster)}\n\n"
        f"{memory}Recent beats:\n{transcript}\n\n"
        f"{direction_block}{owed_block}"
        f"Write these beats, in this order:\n{_plan_block(ctx, decisions)}\n\n"
        f"Mark each beat with its speaker tag, in this order: {' '.join(marks)}\n\n"
        "Write the scene now."
    )
    return system, user


def stream_script(
    db: Session,
    ctx: TurnContext,
    decisions,
    roster: dict[int, str],
    *,
    transcript: str,
    scene_direction: str = "",
    requirements: list[str] | None = None,
    speaker_for_params: CastMember | None = None,
    usage_out: dict | None = None,
) -> Generator[llm.StreamDelta, None, tuple[str, int | None]]:
    """Stream one continuous multi-speaker script; return ``(raw, prompt_tokens)``.

    The sampler is taken from the FIRST speaker and the plan's opening register. A script
    spans several registers and there is only one call to set them on, so this is a genuine
    compromise rather than a neutral choice — and it is one more thing the voiced path does
    better, recorded here rather than glossed.
    """
    base_url, api_key, model, params = resolve_llm(db)
    system, user = build_prompt(
        ctx, decisions, roster,
        transcript=transcript, scene_direction=scene_direction, requirements=requirements,
    )
    register = next((d.register for d in decisions if d.register), None)
    looseness = getattr(speaker_for_params, "looseness", None) if speaker_for_params else None
    tuned = _voice_params(params, register, SCRIPT_EFFORT, None, looseness)
    # Room for every beat in the plan, not one — and bounded BY the plan's length, so a
    # two-beat script cannot spend a ten-beat script's tokens. `_voice_params` sized this for
    # a single beat; a script is several, and the ceiling has to grow with what was planned
    # or the last beat is cut off mid-sentence.
    per_beat = prose_tokens_for() or 2048
    scratchpad = tuned.max_tokens - per_beat if tuned.max_tokens > per_beat else 0
    tuned = tuned.model_copy(
        update={"max_tokens": scratchpad + per_beat * max(1, len(decisions))}
    )
    return (
        yield from llm.chat_complete_stream(
            base_url, api_key, model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tuned,
            reasoning=SCRIPT_EFFORT,
            usage_out=usage_out,
        )
    )

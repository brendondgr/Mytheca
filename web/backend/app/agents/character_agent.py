"""Character authoring agent — the agentic Character Creator (prep phase).

Three creation-time operations run over the configured LLM (same proxy +
settings-store resolution as ``storyline_agent``, via ``agents._common``):

* ``draft_character`` — turn a one-sentence seed (optionally grounded in dropped
  reference docs and the active world) into a full character draft: the by-hand
  fields plus the base-identity prose (appearance / background / personality).
* ``generate_portrait_prompts`` — turn a character description into the
  positive/negative prompts for the watercolor ComfyUI portrait pipeline.
* ``propose_voice_samples`` — derive a voice & tone profile (situation →
  in-voice dialogue-exchange pairs) from a character's background/personality
  (proposal only; runs *before* starting stats so voice/tone is defined first).
* ``propose_starting_stats`` — propose starting values for the storyline's stat
  definitions (proposal only; the caller decides whether to apply them).

Everything produced here is a character's *own* base identity (§1 node
properties of ``Documents/Plans/3.character-graph-structure-prep.md``) — never
graph structure. No edges, no secret nodes, no relationships, no Neo4j.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    LlmConn,
    docs_block,
    rag_block,
    extract_json,
    gen_params,
    resolve_llm,
    resolve_llm_or,
    world_context,
)
from app.core.errors import APIError
from app.schemas.character import (
    CharacterDraftResponse,
    PortraitPromptResponse,
    StartingStatProposal,
    StartingStatsResponse,
    VoiceSample,
    VoiceSamplesResponse,
)
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services import stat_guidance
from app.services import stats as stat_service

# Maximum characters of per-stat guidance text to include in the prompt.
# Long guidance files are trimmed so the prompt stays bounded.
_GUIDANCE_TRIM = 400

_DRAFT_SYSTEM = (
    "You are Velora's character-creation assistant. Given a short description of a "
    "character for an interactive-fiction world, flesh them out. Respond with ONLY "
    "a JSON object — no prose, no markdown, no code fences — with exactly these "
    'string keys: "name" (a fitting proper name), "role" (a short archetype label, '
    "e.g. 'Reluctant Ally'), \"traits\" (3-4 personality adjectives joined with "
    "' · '), \"speech\" (one line on their voice/speech style), \"goal\" (what they "
    'want, one sentence), "secret" (what they hide, one sentence), "appearance" '
    "(3-5 sentences of vivid physical description — species/race if not human, age, "
    "build, face, hair, eyes, distinctive marks, dress, and how they carry "
    'themselves), "background" (3-5 sentences of backstory — origin, formative '
    "events, how they came to be who they are, and current situation), "
    '"personality" (3-5 sentences on temperament, values, fears, quirks, and '
    'mannerisms — concrete and specific, not generic), and "color" (a single accent '
    'hex color that suits them, e.g. "#3A5A78"). Write the three prose fields with '
    "rich, specific detail (avoid one-line summaries). Keep the character consistent "
    "with any world context provided. Include no other keys."
)

_PORTRAIT_SYSTEM = (
    "You are Velora's portrait-prompt writer for a watercolor image model "
    "(Z-Image-Turbo via ComfyUI). The model responds best to SHORT phrases "
    "separated by commas — not sentences. Given a character description, write the "
    "prompts for a flattering character portrait. Respond with ONLY a JSON object "
    '— no prose, no fences — with exactly two string keys: "positive" and '
    '"negative".\n'
    "positive: 10-16 short comma-separated phrases. Lead with the SUBJECT and "
    "their species/race (e.g. 'elderly human woman', 'young orc warrior', "
    "'anthropomorphic red fox', 'elven scholar') — if the character is a specific "
    "race, species, animal, or creature, name it so the image depicts THAT being. "
    "Then their salient features (age, build, hair, eyes, distinctive marks), then "
    "attire, then expression/mood. End with style tags: 'watercolor portrait, soft "
    "washes, painterly, delicate linework, warm lighting, head and shoulders, "
    "detailed face'. Make it read like the person so we know who they are.\n"
    "negative: a comma-separated list of what to avoid, e.g. 'photorealistic, 3d "
    "render, extra limbs, deformed hands, extra fingers, blurry, lowres, text, "
    "watermark, signature, multiple people, cropped face'. Tailor it lightly to the "
    "subject. Keep both prompts concise."
)

_STATS_SYSTEM = (
    "You are Velora's character-creation assistant proposing a character's STARTING "
    "statistics for a world. You are given the world's stat definitions (key, name, "
    "range, default, and any labeled value bands) and a character description. Each "
    "band names what a sub-range MEANS (e.g. health 0-20 = 'nearly dead', 81-100 = "
    "'very healthy') — use those meanings to pick a value whose band matches the "
    "character's intended starting condition. For each stat, propose a starting "
    "integer value within its [min, max] range that fits the character, with a "
    "brief rationale (cite the band meaning when relevant). Respond with ONLY a JSON "
    'object — no prose, no fences — of the form {"proposals": [{"key": "<stat key>", '
    '"value": <int>, "rationale": "<one short line>"}]}. Only use the provided stat '
    "keys. Include every stat."
)


# How many situation → dialogue-exchange pairs to keep (accept 2-4, target 2-3 —
# each pair is now a multi-line exchange, not a single sentence).
_VOICE_SAMPLES_CAP = 4

_VOICE_SYSTEM = (
    "You are Velora's character-voice assistant. Your job is to PROVE, not "
    "describe, how a character talks.\n"
    "First, think through this specific character's actual voice — grounded in "
    "the background, personality, traits, and speech style given below: their "
    "diction (blunt? ornate? clinical?), sentence rhythm (clipped bursts? long "
    "winding clauses?), verbal tics or turns of phrase they lean on, their "
    "default formality, and anything they characteristically avoid saying. Never "
    "default to a generic, textbook-neutral voice — commit to something specific "
    "and a little uneven, the way real speech is.\n"
    "Then write 2-3 distinct situation → exchange pairs that demonstrate this "
    "voice in action. Each \"situation\" is what prompts the character — usually "
    "another character's line of dialogue, or a short vivid beat aimed at them "
    "— written as if it just happened. Each \"sample\" is a FULL back-and-forth "
    "dialogue exchange, not a single line: this character's reply, a brief beat "
    "from the other party, and this character's follow-up — three to five lines "
    "total, alternating speakers, so the reader hears the cadence hold up across "
    "a real conversation. Every line spoken by this character must be "
    "unmistakably theirs (their diction, rhythm, attitude, speech style), and the "
    "register should vary across the pairs (calm, pressured, challenged, warm). "
    "Respond with ONLY a JSON object — no prose, no markdown, no code fences — of "
    'the form {"samples": [{"situation": "<the line or beat that prompts them>", '
    '"sample": "<the full back-and-forth exchange, in their voice>"}]}. Include '
    "no other keys."
)


def _bands_text(definition) -> str:
    """Render a definition's bands as an inline ' Bands: a (lo-hi); …' suffix."""
    bands = definition.bands or []
    if not bands:
        return ""
    parts = [f"{b.get('label', '')} ({b.get('min')}-{b.get('max')})" for b in bands]
    return " Bands: " + "; ".join(parts) + "."


def draft_character(
    db: Session,
    seed: str,
    docs_overview: str | None = None,
    storyline_id: str | None = None,
    *,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
    conn: LlmConn | None = None,
) -> CharacterDraftResponse:
    """Draft a full character (by-hand fields + base-identity prose) from a seed
    and/or dropped reference docs. At least one of the two must be present.

    Pass ``conn`` (a pre-resolved LLM connection) to run on a worker thread without
    touching the request Session — used by the parallel world build."""
    seed = (seed or "").strip()
    has_docs = bool((docs_overview or "").strip())
    if not seed and not has_docs:
        raise APIError(
            400,
            "bad_request",
            "Describe the character in a sentence or add a Draft reference file.",
        )
    base_url, api_key, model, params = resolve_llm_or(db, conn)
    opener = (
        f"Character seed: {seed}"
        if seed
        else "Draft a character grounded in the reference documents below."
    )
    user = (
        f"{opener}{world_context(db, storyline_id)}"
        f"{docs_block(docs_overview)}{rag_block(db, storyline_id, seed)}"
    )
    messages = [
        {"role": "system", "content": _DRAFT_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
        )
    )

    def _s(key: str) -> str:
        return str(data.get(key) or "").strip()

    return CharacterDraftResponse(
        name=_s("name"),
        role=_s("role"),
        traits=_s("traits"),
        speech=_s("speech"),
        goal=_s("goal"),
        secret=_s("secret"),
        appearance=_s("appearance"),
        background=_s("background"),
        personality=_s("personality"),
        color=_s("color"),
    )


def generate_portrait_prompts(
    db: Session,
    *,
    name: str = "",
    role: str | None = None,
    appearance: str | None = None,
    traits: str | None = None,
    personality: str | None = None,
    species: str | None = None,
    notes: str | None = None,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> PortraitPromptResponse:
    """Write the watercolor positive/negative ComfyUI prompts for a character."""
    fields = {
        "Name": name,
        "Role": role,
        "Species/Race": species,
        "Appearance": appearance,
        "Traits": traits,
        "Personality": personality,
        "Notes": notes,
    }
    described = "\n".join(f"{k}: {v}".strip() for k, v in fields.items() if (v or "").strip())
    if not described:
        raise APIError(
            400, "bad_request", "Describe the character (at least a name or appearance) first."
        )
    base_url, api_key, model, params = resolve_llm(db)
    messages = [
        {"role": "system", "content": _PORTRAIT_SYSTEM},
        {"role": "user", "content": f"Character:\n{described}"},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
        )
    )
    return PortraitPromptResponse(
        positive=str(data.get("positive") or "").strip(),
        negative=str(data.get("negative") or "").strip(),
    )


def propose_starting_stats(
    db: Session,
    storyline_id: str,
    *,
    name: str = "",
    role: str | None = None,
    traits: str | None = None,
    personality: str | None = None,
    background: str | None = None,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> StartingStatsResponse:
    """Propose starting values for the storyline's stat definitions (proposal only).

    Returns an empty list (no LLM call) when the world defines no stats. Proposed
    values are clamped to each definition's range and unknown keys are ignored, so
    the caller can apply them straight through the clamped stat endpoint.
    """
    definitions = stat_service.list_stat_definitions(db, storyline_id)
    if not definitions:
        return StartingStatsResponse(proposals=[])
    by_key = {d.key: d for d in definitions}

    base_url, api_key, model, params = resolve_llm(db)

    def _guidance_suffix(d) -> str:
        text = stat_guidance.guidance_for(d)
        if not text:
            return ""
        trimmed = text[:_GUIDANCE_TRIM]
        if len(text) > _GUIDANCE_TRIM:
            trimmed += "…"
        return f"\n  Guidance: {trimmed}"

    schema_lines = "\n".join(
        (
            f"- {d.key} ({d.display_name}): range [{d.min}, {d.max}], default {d.default}."
            f" {d.description}{_bands_text(d)}".rstrip()
            + _guidance_suffix(d)
        )
        for d in definitions
    )
    char_fields = {
        "Name": name,
        "Role": role,
        "Traits": traits,
        "Personality": personality,
        "Background": background,
    }
    described = "\n".join(f"{k}: {v}" for k, v in char_fields.items() if (v or "").strip())
    user = f"Stat definitions:\n{schema_lines}\n\nCharacter:\n{described or name or 'Unnamed'}"
    messages = [
        {"role": "system", "content": _STATS_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = extract_json(
        llm.chat_complete(
            base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
        )
    )

    raw = data.get("proposals")
    rows = raw if isinstance(raw, list) else []
    proposals: list[StartingStatProposal] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        definition = by_key.get(key)
        if definition is None or key in seen:
            continue
        raw_value = row.get("value")
        try:
            if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                value = int(raw_value)
            else:
                value = int(str(raw_value).strip())
        except (TypeError, ValueError):
            value = definition.default
        value = max(definition.min, min(definition.max, value))
        seen.add(key)
        proposals.append(
            StartingStatProposal(
                key=key,
                display_name=definition.display_name,
                value=value,
                min=definition.min,
                max=definition.max,
                rationale=str(row.get("rationale") or "").strip(),
            )
        )
    # Fill any stat the model skipped with its default, so the proposal is complete.
    for d in definitions:
        if d.key not in seen:
            proposals.append(
                StartingStatProposal(
                    key=d.key,
                    display_name=d.display_name,
                    value=d.default,
                    min=d.min,
                    max=d.max,
                    rationale="",
                )
            )
    return StartingStatsResponse(proposals=proposals)


def propose_voice_samples(
    db: Session,
    *,
    name: str = "",
    role: str | None = None,
    traits: str | None = None,
    speech: str | None = None,
    background: str | None = None,
    personality: str | None = None,
    storyline_id: str | None = None,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
    conn: LlmConn | None = None,
) -> VoiceSamplesResponse:
    """Derive a voice & tone profile (situation → dialogue-exchange pairs) for a character.

    Grounded in the drafted background/personality/speech (and the active world) so
    the samples match the character's tone. Best-effort: returns an empty list rather
    than raising when there's nothing to describe or the LLM misbehaves — the caller
    decides whether to apply the proposal. Kept to at most ``_VOICE_SAMPLES_CAP`` pairs.
    """
    char_fields = {
        "Name": name,
        "Role": role,
        "Traits": traits,
        "Speech style": speech,
        "Background": background,
        "Personality": personality,
    }
    described = "\n".join(f"{k}: {v}" for k, v in char_fields.items() if (v or "").strip())
    if not described:
        return VoiceSamplesResponse(samples=[])

    base_url, api_key, model, params = resolve_llm_or(db, conn)
    user = f"Character:\n{described}{world_context(db, storyline_id)}"
    messages = [
        {"role": "system", "content": _VOICE_SYSTEM},
        {"role": "user", "content": user},
    ]
    try:
        data = extract_json(
            llm.chat_complete(
                base_url, api_key, model, messages, gen_params(params), reasoning=reasoning
            )
        )
    except Exception:  # best-effort — a bad/absent generation yields no samples
        return VoiceSamplesResponse(samples=[])

    raw = data.get("samples")
    rows = raw if isinstance(raw, list) else []
    samples: list[VoiceSample] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sample = str(row.get("sample") or "").strip()
        if not sample:
            continue
        situation = str(row.get("situation") or "").strip()
        samples.append(VoiceSample(situation=situation, sample=sample))
        if len(samples) >= _VOICE_SAMPLES_CAP:
            break
    return VoiceSamplesResponse(samples=samples)

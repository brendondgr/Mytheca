"""Play (turn-loop) request + session-review schemas.

``POST /api/play/{scenarioId}/turn`` submits one player turn and streams the
resulting story events back as NDJSON (the response is the stream itself — there is
no JSON response body). The terminal in-band error frame is
``app.events.stream.TurnErrorFrame``. The session-review schemas below back the
persistent-scene endpoints (``GET …/sessions``, ``GET …/sessions/{id}`` history, and
``POST …/sessions/{id}/close``) so a scenario's play-through can be reopened and
continued with its full history — turns, thoughts, and the graph/RAG trace — intact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.base import BeatLength, CamelModel, PresenceStatus, Visibility

# One engine, two render styles (D1): POV (interstitials off) or Playwright (on).
#
# The wire spelling is still ``"narrator"`` — a legacy value kept because the field is
# deprecated and inert (below), and renaming a dead enum would break callers for nothing.
# It names the PLAYER'S mode, not the Narrator agent.
#
# **Deprecated and inert.** It reaches exactly one place in the engine (the `turn` trace
# payload) and changes nothing about how a turn runs. Kept on the request so no existing
# caller breaks; deliberately never surfaced in the UI. See `TurnRequest`.
TurnMode = Literal["pov", "narrator"]


class PresenceRequest(CamelModel):
    """A manual player override of a character's scene presence (Scene Presence & Director
    Actions).

    Sets ``characterId`` to any :data:`~app.schemas.base.PresenceStatus` on the given
    session — including a resurrection back to ``present`` (the player has final say; the
    endpoint is intentionally not bound by the engine's ``can_transition`` guard). Persists a
    ``character_status_change`` event with ``auto=False`` so the client does NOT show an
    undo toast (a manual change is already the player's intent)."""

    session_id: str
    character_id: str
    status: PresenceStatus
    reason: str = ""


class TurnDirective(CamelModel):
    """One line of the player's direction, with the character they aimed it at.

    The direction box is read **per line**: each line is one thing the turn owes, and an
    ``@`` cast mention on that line pins ``actorId`` to that character. When the player
    supplies these, the engine uses them verbatim and does **not** call
    ``direction_agent.parse`` — they already said what and who, so a round-trip to re-guess
    it is slower and worse. A pinned target is never silently re-owned by the narrator; if
    that character is not in the scene, the requirement waits rather than being handed to
    someone else.
    """

    text: str
    actor_id: str | None = None


#: How a beat is pitched — the planner's read of the moment, on one axis from banter to
#: life-and-death. Mirrors ``planner_agent._REGISTERS``.
Register = Literal["light", "neutral", "tense", "grave"]

#: How much of a speaker's relationship history reaches their beat.
#: ``None`` reads as ``"scene"``.
TieScope = Literal["addressed", "scene", "world"]

#: How a turn's prose is produced.
#:
#: * ``"voiced"`` — one model call per speaker, each carrying that character's voice samples,
#:   register and relationship note. What has always shipped, and what keeps voices apart.
#: * ``"continuous"`` — ONE call writes the whole planned turn, marking each change of speaker
#:   with ``<speaker:N>``. Flows better and attributes from a token the writer emitted rather
#:   than from the engine guessing; the cost is that every voice sample shares one prompt.
#:
#: ``None`` reads as ``"voiced"``. See ``agents/scene_script_agent`` for the trade in full and
#: ``docs/checklist.md`` for the experiment that would settle which is better.
SceneFlow = Literal["voiced", "continuous"]

#: How the turn's plan is used.
#:
#: * ``"auto"`` — the planner decides each beat and the turn plays straight through. This is
#:   the behaviour that shipped as ``"planner"``, which is still accepted and reads as this.
#: * ``"plan"`` — the planner runs, the plan is streamed to the player as a ``plan`` frame,
#:   and the turn **stops there**. Nothing is written until the player sends it back on
#:   ``TurnRequest.approvedPlan``.
#: * ``"off"`` — no planner call at all; ``services/beat_order`` decides who is next. A
#:   different kind of choice from the two above (it changes what the app *is*, not whether
#:   you approve its output), which is why the composer's Plan-mode control offers only the
#:   first two and this one stays in the Config popover.
#:
#: ``None`` reads as ``"auto"``.
PlannerMode = Literal["auto", "plan", "planner", "off"]


class TurnOverrides(CamelModel):
    """Scene settings applied to **this turn only**.

    Every field is optional and ``None`` by default; an unset field falls back to the
    ``Scenario`` row. Nothing here is ever written to that row — the override is spent when
    the turn ends, which is the whole point: a player can try a longer beat, or silence the
    follow-up suggestions for one message, without editing the scene they will keep playing.

    It is out of scope for the intent, direction and planner agents in exactly the way
    ``taggedDocIds`` is out of scope for them. An override changes how the turn is **run** —
    how many beats it may produce, how much a character says, whether follow-ups are offered
    — and never what the turn is **about**. No agent is shown it, so it cannot decide what
    happens, who acts, or where the scene goes.

    ``maxTurns`` and ``beatLength`` used to live here and are **gone**: how many beats a
    message makes, and how long a beat is, are now decided by the scene rather than set. An
    old client still sending them is not an error — pydantic ignores unknown fields, so the
    envelope is accepted and the values have no effect, which is the right outcome for a
    control that no longer exists.
    """

    suggestions_count: int | None = Field(default=None, ge=0, le=4)
    #: ``"off"`` runs the turn on ``services/beat_order`` instead of the planner — no model
    #: call for beat selection, and no register, stakes, narrator interstitials or exits.
    planner: PlannerMode | None = None
    #: Pin how this moment is pitched, for this turn only. **Per-turn by design and there is
    #: no ``Scenario`` column for it** — "how tense this beat is" is a property of a moment,
    #: not of a scene, so a persisted one would be wrong by the second message. It outranks
    #: the planner's own read wherever the two disagree.
    #:
    #: The wire name is ``register``; the Python attribute is not, because ``register`` is
    #: ``ABCMeta.register`` on the model's metaclass and pydantic warns about the shadow on
    #: every import. An explicit alias keeps the contract exactly as documented and keeps the
    #: suite free of a warning that would have to be explained to every future reader.
    beat_register: Register | None = Field(default=None, alias="register")
    #: How wide a speaker's remembered history is for this turn — see ``TieScope``.
    ties: TieScope | None = None
    #: How this turn's prose is produced — see :data:`SceneFlow`.
    scene_flow: SceneFlow | None = None


class ApprovedBeat(CamelModel):
    """One beat of a plan the player has approved, as it comes back on the next request.

    Deliberately the *decision*, not the prose: the player approves who acts and what they
    are trying to do, and the writing still happens fresh. Approving a plan is not the same
    as dictating lines, and an approved plan that carried text would quietly become the
    second of those.
    """

    action: str
    actor_id: str | None = None
    addressing_id: str | None = None
    reason: str = ""
    #: Aliased for the same reason as ``TurnOverrides.beat_register`` — ``register`` shadows
    #: ``ABCMeta.register`` on the metaclass and pydantic warns on every import.
    beat_register: Register | None = Field(default=None, alias="register")
    stakes: str = ""
    status: str | None = None


class TurnRequest(CamelModel):
    """One player turn.

    ``sessionId`` resumes an existing play session; omit it to start a new one.
    ``directedAt`` is the optional character id the player is addressing — now set by the UI
    from an ``@`` cast mention in the message box. ``trace`` opts into diagnostic ``trace``
    frames interleaved on the stream (the story player's Inspector panel) — off by default so
    the default stream + the story-event contract are unchanged. ``outcome`` is the
    narrative-direction tag of a branch/path the player selected: the turn opens with a fuller
    "progression" narration that plays the choice out over several beats, and the story
    player's **"Play it out"** action on a suggestion chip is what sends it.

    **``mode`` is deprecated and inert.** It reaches exactly one place in the engine — the
    ``turn`` trace payload — and changes nothing about how a turn runs. It is still accepted
    so no existing caller breaks, and it is deliberately **not** exposed in the UI: narrator
    interstitials are decided by the planner from the scene, which is a better answer than a
    switch the player has to understand. That is a decision, not an omission; see
    ``docs/architecture.md``.

    ``povCharacterId`` is the *Player POV* control: when set to a present cast member's
    id, the player's line **is that character's line** — it is seeded into the turn as a
    ``character`` beat (so later speakers react to *Mei said X*), persisted on the
    ``user_turn`` row, and the POV character is removed from the AI's selectable roster so
    it is never voiced by the model. ``None`` (the default) is today's guide/narrator
    behavior. NOTE: this is orthogonal to ``mode`` — ``mode`` is a *rendering* switch
    (narrator interstitials on/off); ``povCharacterId`` is *who the player speaks as*.

    ``guidance`` is the *narrator direction* for the turn — what should happen next and how
    the cast should react — sent from the story player's second composer box, which appears
    above the message box whenever ``povCharacterId`` is set. It exists because under Player
    POV the ``text`` field is the character's own line and can no longer double as
    direction. The engine parses it into ``direction_agent`` requirements and schedules them
    across the scene's ``maxTurns`` budget, so everything asked for lands inside the turn.
    When it is omitted **and** POV is off, the player's ``text`` is itself the direction
    (the main box is the narrator box); when it is omitted under POV, the turn carries no
    direction at all. Vague ("things get worse") and highly specific ("Mei storms out,
    Aldous grabs her wrist, the lamp goes over") both work — the more it asks for, the more
    of the turn's beats are committed to delivering it.

    A selected follow-up suggestion no longer submits a turn on its own: the story player
    writes the suggested text into the composer for the player to review/edit and send as
    an ordinary ``text`` turn (request #2), so there is no separate open-ended steer field.

    ``taggedDocIds`` are the storyline ``ContextDocument`` ids the player **@-tagged** in the
    composer. Their text is loaded server-side and folded into the character + narrator
    prompts as **reference material for this one turn**, bypassing the conservative
    ``retrieval_gate`` (which skips most turns) and the 600-character RAG snippet cap. It is
    the exact opposite of ``guidance``: guidance is *direction* and becomes schedulable
    requirements; tagged files are *background* and never do. Structurally, tagged text is
    withheld from ``intent_agent``, ``direction_agent`` and ``planner_agent``, so it can
    inform what a character or the narrator SAYS but can never decide what happens, who
    acts, or where the scene goes. Ids belonging to another storyline are ignored, and the
    text is bounded (see ``assembler.TAGGED_*``).
    """

    session_id: str | None = None
    text: str
    directed_at: str | None = None
    mode: TurnMode = "pov"
    trace: bool = False
    outcome: str | None = None
    pov_character_id: str | None = None
    guidance: str | None = None
    tagged_doc_ids: list[str] = Field(default_factory=list)
    #: The player pressed *Continue*: run a turn with no line from them at all. The scene
    #: simply carries on. Combined with the relaxed validation in
    #: ``turn_engine.validate_turn_inputs``, this is what lets a player watch rather than
    #: always having to speak to move a scene forward.
    continuation: bool = False
    #: The direction box read line-by-line, each line optionally aimed at a character the
    #: player ``@``-mentioned on it. Non-empty ``directives`` **replace** ``guidance`` parsing:
    #: the engine builds the requirements from them directly. Empty (the default) keeps
    #: today's behaviour exactly — free prose in the box is parsed by ``direction_agent``.
    directives: list[TurnDirective] = Field(default_factory=list)
    #: A plan the player approved, sent straight back from the ``plan`` frame of a turn that
    #: stopped for approval. When present the engine **executes it without re-planning** —
    #: that is the whole point, since re-planning would produce a different turn from the one
    #: that was approved. Roster-checked all the same: presence can change between the plan
    #: being shown and it being sent, and a beat naming somebody who has since left is
    #: dropped rather than run.
    approved_plan: list[ApprovedBeat] = Field(default_factory=list)
    #: Scene settings for this turn only — see :class:`TurnOverrides`. Never written to the
    #: ``Scenario`` row, never shown to an agent, and persisted on the ``user_turn`` row only
    #: so the Inspector and the export can say what the turn actually ran with.
    overrides: TurnOverrides | None = None


class SessionSummary(CamelModel):
    """One play-through's metadata for the tray (newest ``updatedAt`` first).

    ``turnCount`` is the number of player turns taken; ``preview`` is the first non-empty
    player line. ``name`` is the player's own label, and the tray falls back to
    ``preview`` when it is unset. ``parentSessionId`` + ``forkSeq`` are set together on a
    play-through that was branched from another (and on the snapshot a rewind keeps),
    recording which session it came from and the seq the copy ran through.
    """

    id: str
    scenario_id: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    turn_count: int = 0
    preview: str = ""
    name: str | None = None
    parent_session_id: str | None = None
    fork_seq: int | None = None
    #: The highest ``Event.seq`` the scene's rolling memory covers, so a reload knows where
    #: verbatim recall ends without a second request. ``None`` when nothing is summarised.
    summary_through_seq: int | None = None


class SessionCreateRequest(CamelModel):
    """Start a fresh play-through of a scenario. An optional label; nothing else is
    needed, because a new session opens empty and the first turn fills it."""

    name: str | None = None


class SessionRenameRequest(CamelModel):
    """Relabel a play-through. A blank name clears the label, restoring the
    first-player-line fallback."""

    name: str | None = None


class BranchRequest(CamelModel):
    """Fork a play-through at a beat, leaving the original untouched.

    ``atEventId`` is any event in the transcript; the fork point is the end of the **turn**
    that event belongs to, so the branch inherits whole turns rather than half of one.
    ``expectedSeq`` is the client's view of the session's highest seq — a mismatch means the
    play-through moved on (another tab, a turn that finished) and the request 409s.
    """

    at_event_id: str
    name: str | None = None
    expected_seq: int | None = None


class RewindRequest(CamelModel):
    """Cut a play-through back to a beat and carry on from there.

    The cut is at a **turn boundary**: the turn containing ``atEventId`` goes, along with
    everything after it. ``keepSnapshot`` (default true) forks the pre-cut history into its
    own play-through first, so the undo is a row in the tray rather than a hidden ten-second
    window — and no ``deleted_at`` column every other query would have to filter.
    """

    at_event_id: str
    keep_snapshot: bool = True
    expected_seq: int | None = None


class RestoredTurn(CamelModel):
    """The player's own line, handed back so the scene can continue from it.

    This is what makes a rewind a *prompt* rather than just a deletion: the words come back
    into the composer, editable, with the direction and attachments they rode in with (all
    persisted on the ``user_turn`` row).
    """

    text: str = ""
    guidance: str | None = None
    pov: str | None = None
    tagged_doc_ids: list[str] = Field(default_factory=list)


class RewindResponse(CamelModel):
    """What the cut removed, and what the player gets back."""

    session: SessionSummary
    cut_seq: int
    removed_events: int = 0
    removed_traces: int = 0
    #: The play-through holding the removed history, when ``keepSnapshot`` was set.
    snapshot_session_id: str | None = None
    restored_turn: RestoredTurn | None = None


class BeatEditRequest(CamelModel):
    """Rewrite one beat's prose.

    Allowed on any beat that *has* prose — narration, a character's passage, and the player's
    own lines. Machinery beats (a stat change, a set of choices) have nothing to rewrite and
    are refused with a 422 rather than silently ignored.
    """

    text: str
    expected_seq: int | None = None


class RerollRequest(CamelModel):
    """Generate another version of a beat.

    ``scope`` of ``beat`` re-runs that beat alone, in place, against the context it
    originally saw. ``turn`` re-runs the whole turn it belongs to — the owner asked for both,
    because a beat that went wrong because the *turn* went wrong is not fixed by re-rolling
    one line of it.
    """

    scope: Literal["beat", "turn"] = "beat"
    expected_seq: int | None = None


class TakeSelectRequest(CamelModel):
    """Show one of a beat's kept versions."""

    take: int


class GhostwriteRequest(CamelModel):
    """Draft the player's own line from a note about what they want it to do.

    ``intent`` is the note ("tell him I don't believe a word of it, but stay polite"), not
    text to paraphrase. ``mode`` picks whose voice: the POV character's, or the narrator's.
    Nothing is persisted — the draft lands in the composer and the player decides.
    """

    session_id: str
    intent: str
    pov_character_id: str | None = None
    mode: Literal["character", "narrator"] = "character"


class RecapRequest(CamelModel):
    """Ask for prose describing what has happened up to a point in the scene.

    ``throughSeq`` defaults to the whole scene. It exists so the request can mean "recap
    everything above the line where verbatim memory stops", which is the question the memory
    panel actually asks.
    """

    through_seq: int | None = None


class RecapResponse(CamelModel):
    """What happened, in prose. ``""`` when there is nothing to say or no model to say it."""

    text: str = ""


class SceneKnowledgeRetrieval(CamelModel):
    """Whether the world-lore lookup ran this turn, and what came of it."""

    fired: bool = False
    reason: str = ""
    matched: bool = False


class SceneKnowledgeDirection(CamelModel):
    """What the player asked the scene to do, and what of it the turn confirmed."""

    text: str = ""
    items: list[str] = Field(default_factory=list)
    delivered: list[str] = Field(default_factory=list)
    outstanding: list[str] = Field(default_factory=list)


class SceneKnowledgeSummary(CamelModel):
    """The scene's rolling memory of beats that fell out of the context window."""

    text: str = ""
    through_seq: int | None = None
    updated_at: datetime | None = None


class SceneKnowledgeResponse(CamelModel):
    """What the scene knows right now, in the player's terms.

    The Inspector answers *"what did the loop do"*; this answers *"what does the scene know"*.
    Assembled from the most recent turn's persisted trace rows plus the session's summary
    columns, so it costs the turn path nothing and — the point — works on a **resumed** scene,
    which is exactly when a player most wants to ask what a long session still remembers.

    Every field degrades to empty rather than absent: a session with no turns yet is a
    legitimate question whose honest answer is a set of zeroes.
    """

    window_beats: int = 0
    window_source: str = ""
    dropped_beats: int = 0
    budget_tokens: int = 0
    #: The endpoint's own input-token count for the last character call — the one
    #: non-estimated number here, absent when the endpoint reported none.
    prompt_tokens: int | None = None
    tagged_names: list[str] = Field(default_factory=list)
    retrieval: SceneKnowledgeRetrieval = Field(default_factory=SceneKnowledgeRetrieval)
    relationships: list[str] = Field(default_factory=list)
    direction: SceneKnowledgeDirection = Field(default_factory=SceneKnowledgeDirection)
    summary: SceneKnowledgeSummary = Field(default_factory=SceneKnowledgeSummary)


class SessionListResponse(CamelModel):
    sessions: list[SessionSummary]


class PersistedEvent(CamelModel):
    """A stored story event in the wire-envelope shape, so the story player can replay
    it through the exact same reducers it uses for the live stream (reload = replay)."""

    type: str
    id: str
    seq: int
    scenario_id: str
    session_id: str
    ts: datetime
    visibility: Visibility
    data: dict[str, Any]


class PersistedTrace(CamelModel):
    """A stored diagnostic trace step (graph/RAG/thinking) for one turn, ordered by
    ``(turn, n)`` — folds back into the Inspector exactly like a live ``trace`` frame."""

    turn: int
    n: int
    step: str
    title: str
    detail: str
    data: dict[str, Any]


class StandingItem(CamelModel):
    """One thing the player is still owed, surviving from an earlier turn.

    ``fromTurn`` is the seq of the turn it was **first** asked for — not the turn it most
    recently failed on, so the checklist's "carried over" badge reflects age. ``actorId`` is
    who it is aimed at, and ``pinned`` says the player named them (so it is waiting for that
    character rather than being available to the narrator).
    """

    id: str
    text: str
    actor_id: str | None = None
    pinned: bool = False
    from_turn: int | None = None


class StandingDirectionRequest(CamelModel):
    """Stop asking for some of what is still owed.

    ``itemIds`` names the entries to drop; ``None`` clears the whole debt. A standing
    direction the player cannot cancel would be a bug rather than a feature — they have to
    be able to change their mind about something the scene has not managed to do.
    """

    item_ids: list[str] | None = None


class StandingDirectionResponse(CamelModel):
    """What is still owed after the change."""

    standing_direction: list[StandingItem]


class SessionHistoryResponse(CamelModel):
    """The full record of one play-through: metadata + every event (incl. hidden
    thoughts + the ``user_turn`` rows) + every diagnostic trace step."""

    session: SessionSummary
    events: list[PersistedEvent]
    traces: list[PersistedTrace]
    #: What an earlier turn could not deliver, so a resumed scene can show the debt it is
    #: about to re-owe rather than surprising the player with it mid-turn.
    standing_direction: list[StandingItem] = Field(default_factory=list)


# ---- in-narrative image generation (the player's "Create image" action) -----


class MomentPromptResponse(CamelModel):
    """The prompts ``agents.moment_agent`` wrote for a picture of the current moment.

    ``positive`` describes the moment in ComfyUI phrase form — every figure by
    appearance and action, never by name (enforced by ``moment_agent.strip_names``).
    ``caption`` is plain English for a reader who cannot see the image, and MAY use
    names; it becomes the event's alt text.
    """

    positive: str
    negative: str = ""
    caption: str = ""


class MomentRequest(CamelModel):
    """Ask for a picture of where the scene stands right now.

    ``sessionId`` is required — a moment belongs to a play-through, and the beats it
    depicts are read from that session's event log. ``beats`` optionally narrows how
    far back the shot looks (defaults to the scenario's own ``contextBeats`` window,
    clamped); everything else (who is in frame, the place, the world) is derived
    server-side, so the client cannot desync from the story.
    """

    session_id: str
    beats: int | None = None
    #: The player's own wording, from the enlarged view's editable prompt. When present the
    #: ``moment_agent`` call is skipped entirely — they have said what they want painted, and
    #: re-deriving it would both cost a call and override them. Still passed through
    #: ``moment_agent.strip_names``, so the no-character-names guarantee is not bypassed by
    #: hand-written input.
    prompt: str | None = None
    negative: str | None = None
    #: Which look to paint in (``app.content.art_styles``). Omitted = the operator's stored
    #: default. Unknown ids fall back to the default rather than failing the render.
    art_style: str | None = None


class MomentStageFrame(CamelModel):
    """Progress on the moment stream: which of the two stages is running.

    ``prompt`` while the agent writes, ``render`` while ComfyUI paints (re-emitted as
    the keep-alive heartbeat so a silent socket never looks dead). ``positive`` is
    filled once the prompt exists, so the UI can show what is being painted.
    """

    type: Literal["moment_stage"] = "moment_stage"
    stage: Literal["prompt", "render"]
    message: str = ""
    positive: str = ""
    caption: str = ""

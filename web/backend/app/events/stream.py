"""Stream helpers: envelope construction + NDJSON serialization.

The turn engine builds typed story events through :func:`build_event` (so every
emitted event is validated against the discriminated union by construction) and
serializes them to NDJSON lines via :func:`to_ndjson_line` — the same
``model_dump_json(by_alias=True) + "\\n"`` shape the build/triage streams use.

Delta-streaming wrapper frames (``message_start`` / ``message_delta`` /
``message_end``) are added in a later phase; for now visible messages stream as
full events.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.ids import new_id
from app.events.envelope import StoryEvent, story_event_adapter
from app.schemas.base import CamelModel, EventType, Visibility


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (the envelope ``ts``)."""
    return datetime.now(UTC).isoformat()


def build_event(
    type_: EventType,
    data: dict[str, Any],
    *,
    scenario_id: str,
    session_id: str,
    seq: int,
    visibility: Visibility | None = None,
    event_id: str | None = None,
    ts: str | None = None,
) -> StoryEvent:
    """Construct and validate a single story event.

    Returns the concrete typed model (e.g. ``CharacterDialogueEvent``) via the
    discriminated-union adapter, so an invalid ``type``/``data`` shape raises here
    rather than slipping onto the wire. ``visibility`` defaults to the type's own
    default (``hidden`` for ``internal_thought``, else ``public``) when omitted.
    """
    payload: dict[str, Any] = {
        "type": type_,
        "id": event_id or new_id("ev"),
        "seq": seq,
        "scenario_id": scenario_id,
        "session_id": session_id,
        "ts": ts or now_iso(),
        "data": data,
    }
    if visibility is not None:
        payload["visibility"] = visibility
    return story_event_adapter.validate_python(payload)


def to_ndjson_line(frame: BaseModel) -> str:
    """Serialize a story event (or transport frame) to one NDJSON line."""
    return frame.model_dump_json(by_alias=True) + "\n"


# Visible prose (narration, character_dialogue) is delta-streamed by emitting the
# **same event** (same id + seq) repeatedly with incremental ``text`` and ``done:
# false`` until the final chunk sets ``done: true`` — the client accumulates by id.
# This reuses the ``done`` field already on those payloads; the persisted row holds
# the full text. (``character_action`` has no ``done`` field and streams as one event.)
_DELTA_CHUNK_CHARS = 48


def chunk_text(text: str, max_chunk_chars: int = _DELTA_CHUNK_CHARS) -> list[str]:
    """Split text into incremental delta chunks; ``"".join(chunks) == text`` exactly.

    Chunks break only on word boundaries (the breaking space stays at the end of the
    chunk), so concatenating them on the client reconstructs the text verbatim.
    Always returns at least one chunk (``[""]`` for empty text).
    """
    if not text:
        return [""]
    chunks: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + max_chunk_chars, n)
        if end < n:
            space = text.find(" ", end)
            end = space + 1 if space != -1 else n  # keep the space with this chunk
        chunks.append(text[start:end])
        start = end
    return chunks


# How long a stream may stay silent before a keep-alive frame goes out. Well under
# any conventional idle-connection reaping (proxies commonly reap at 30-60s) and far
# too coarse to matter as traffic.
KEEPALIVE_INTERVAL_SECONDS = 10.0


def with_keepalive(
    source: Iterable[Any],
    keepalive: Callable[[], Any],
    interval: float = KEEPALIVE_INTERVAL_SECONDS,
) -> Iterator[Any]:
    """Yield from ``source``, emitting ``keepalive()`` every ``interval`` idle seconds.

    An agent turn calls the LLM to completion *before* its first ``yield``, so the
    response holds a socket that is byte-for-byte silent for the whole generation —
    measured at 24s for one storyline turn, and minutes on a large local reasoning
    model. Response headers go out immediately, so nothing on the wire says the work
    is still alive, and any idle-connection reaping between browser and server takes
    the stream down mid-thought.

    ``source`` runs on a daemon worker thread feeding a queue; this generator polls
    with a timeout and fills the gaps. The worker owns the request's ``Session``
    exclusively while the request thread blocks on the queue, so the two never touch
    SQLAlchemy concurrently. Items and exceptions are relayed **in order**, leaving
    the caller's error handling (e.g. an ``APIError`` becoming a terminal error frame)
    exactly as it was without the wrapper.
    """
    done = object()
    relay: queue.Queue = queue.Queue()

    def pump() -> None:
        try:
            for item in source:
                relay.put((None, item))
        except BaseException as exc:  # relayed and re-raised on the consumer thread
            relay.put((exc, None))
        finally:
            relay.put((None, done))

    # Daemon: if the client disconnects, the worker finishes its in-flight LLM call
    # (bounded by the generation timeout) and exits rather than holding shutdown.
    threading.Thread(target=pump, name="stream-keepalive", daemon=True).start()

    while True:
        try:
            exc, item = relay.get(timeout=interval)
        except queue.Empty:
            yield keepalive()
            continue
        if exc is not None:
            raise exc
        if item is done:
            return
        yield item


class BeatRerollFrame(CamelModel):
    """A re-roll is starting for an existing beat: **clear its text** before what follows.

    A transport frame, not a persisted story event — nothing about it belongs in the record.
    The deltas after it are ordinary story-event frames re-emitting the same ``id`` and
    ``seq``, so the client's accumulator needs no special case; this frame exists only
    because those deltas would otherwise append to the take being replaced.
    """

    type: Literal["beat_reroll"] = "beat_reroll"
    event_id: str
    #: The index the new take will occupy once it completes.
    take: int = 0


class GhostwriteFrame(CamelModel):
    """One increment of a ghostwritten line.

    Incremental like every other delta in this codebase — the client appends. Nothing here
    is ever persisted: the draft exists only in the composer until the player sends it.
    """

    type: Literal["ghostwrite"] = "ghostwrite"
    text: str = ""
    done: bool = False


class TurnErrorFrame(CamelModel):
    """Terminal in-band error frame for the turn stream.

    Mirrors ``TriageErrorEvent`` / ``AgentErrorFrame``: pre-flight failures return a
    normal ``400`` before the ``200`` stream opens, but a mid-stream failure can only
    be reported in-band, so the route yields this as the final line.
    """

    type: Literal["error"] = "error"
    message: str


class TurnReasoningFrame(CamelModel):
    """The model's in-flight deliberation, streamed live and **never persisted**.

    A transport frame like :class:`TurnTraceFrame`, carrying the ``reasoning_content``
    channel a reasoning endpoint reports alongside its answer — the text the app used to
    read and discard. It is the machine's scratchpad, not story record: it is not a story
    event, gets no ``seq``, is not written to ``events`` or ``turn_traces``, and does not
    come back on resume or in an export.

    Emitted only when the operator sets Reasoning visibility to ``full``; the default
    keeps it off the wire entirely, because raw deliberation routinely states what a
    character is about to say before they say it.
    """

    type: Literal["reasoning"] = "reasoning"
    character_id: str | None = None
    text: str = ""
    done: bool = False


class PlannedBeat(CamelModel):
    """One beat of a plan, as the player is shown it and as they may send it back."""

    action: str  # "speak" | "narrate" | "exit" | "end"
    actor_id: str | None = None
    actor_name: str = ""
    addressing_id: str | None = None
    #: The planner's own short why. Shown as the beat's description, because it is already
    #: written for a reader — "she is not going to let that stand" — rather than as a label.
    reason: str = ""
    #: The wire name is ``register``; the Python attribute is not, because ``register`` is
    #: ``ABCMeta.register`` on the model's metaclass and pydantic warns about the shadow on
    #: every import. Same alias, same reason, as ``TurnOverrides.beat_register``.
    beat_register: str | None = Field(default=None, alias="register")
    stakes: str = ""
    status: str | None = None


class TurnPlanFrame(CamelModel):
    """The turn's plan, streamed before any prose is written.

    A **transport** frame, not a story event: a plan is a statement of intent that may never
    happen, and persisting one would put something in the transcript that no reader ever saw
    and no rewind could account for.

    Emitted on every planned turn so the Inspector can show what the scene decided. Under
    ``PlannerMode`` ``"plan"`` it is also the point the turn **stops**: nothing is generated,
    and the player either approves the plan — sending it back on ``TurnRequest.approvedPlan``,
    which the engine executes without re-planning — or edits their direction and sends again.

    ``awaitingApproval`` says which of those two this is, so the client does not have to infer
    it from the scene's current mode: the mode can change between a turn being sent and its
    frames arriving, and a plan panel that appeared over an already-running turn would offer
    an approval that cannot apply to it.
    """

    type: Literal["plan"] = "plan"
    #: The session this plan belongs to. **Load-bearing under ``"plan"``**: that turn stops
    #: before any story event is emitted, and story events are the only other frames that
    #: carry a session id — so without this a client starting a new session would have
    #: nothing to send the approval back on, and every approved plan would open a second
    #: session and replay the scene from nothing.
    session_id: str = ""
    beats: list[PlannedBeat] = Field(default_factory=list)
    awaiting_approval: bool = False


class TurnTraceFrame(CamelModel):
    """Diagnostic trace frame for the turn stream (opt-in via ``TurnRequest.trace``).

    **Not** a persisted story event — a transport frame (like :class:`TurnErrorFrame`)
    the engine interleaves to explain, in order, what the turn loop did and *why*: the
    Director's speaker choice + rationale, each character's hidden thinking, stat clamps,
    the mid-turn re-rank / cascade, the reflection interlude. The story player's
    **Inspector** panel renders these in order; the transcript ignores them. Emitted only
    when the caller sets ``trace: true``, so the default stream and the story-event
    contract are unchanged. ``n`` orders the frames within one turn; ``step`` is a stable
    machine key (``turn`` opens each turn); ``title``/``detail`` are human-readable and
    ``data`` carries the structured payload (speakers, deltas, order changes, …)."""

    type: Literal["trace"] = "trace"
    n: int = 0
    step: str
    title: str
    detail: str = ""
    data: dict = Field(default_factory=dict)

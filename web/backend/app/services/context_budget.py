"""How much of the scene fits in the model's context, in one place.

The transcript depth used to be a per-scene slider — *"Number of beats"* — which asked the
player to pick a number whose only honest answer is "as much as the model can hold". The
owner's word for it was "stupid", and they were right twice: the player cannot know the
answer, and the app already can.

**Everything that needs to know the budget reads this module.** Before it, the composer's
context dial and the turn engine would each have hit
``GET /options/llm/context-window`` independently — two reads of one truth, free to drift.
The route now delegates here, so the number the player is shown and the number the engine
budgets against are provably the same value.

**The load-bearing detail is quantisation.** ``buffer.anchored_turns`` keeps the rendered
transcript's *prefix* byte-stable by moving the window's start in blocks of
``TURN_TRANSCRIPT_ANCHOR_BLOCK``; a prefix cache matches from the first token, so a window
that slid by one beat per turn would re-prefill the whole transcript every turn. A *dynamic*
depth threatens that directly — a depth that changes by one beat has exactly the same effect.
So :func:`fit_window` quantises the depth it computes **down** to a multiple of the block,
and only shrinks when the overage is at least a whole block. The window can therefore only
change in the same steps the anchoring already tolerates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.rag.tokens import approx_tokens
from app.services import llm_backend, settings_store

WindowSource = Literal["detected", "configured", "fallback"]


@dataclass(frozen=True)
class WindowInfo:
    """The model's context window, and how confidently we know it."""

    max_tokens: int
    #: ``detected`` — the engine reported it; ``configured`` — the operator's setting;
    #: ``fallback`` — neither was usable, so a conservative default is in force. The
    #: distinction is shown to the player, because "we asked the model" and "we guessed"
    #: are different claims and only one of them should be trusted with a full window.
    source: WindowSource


@dataclass(frozen=True)
class FitResult:
    """How many recent beats fit, and what that costs."""

    window_beats: int
    dropped_beats: int
    used_tokens: int


def resolve_window(db: Session) -> WindowInfo:
    """The effective context window for the configured endpoint.

    Probe the engine first; fall back to the operator's ``maxContextTokens`` setting; fall
    back again to a conservative default when that is unset or nonsensical. The last case is
    reported as ``fallback`` rather than dressed up as ``configured`` — the engine must be
    able to tell "the operator chose 4096" from "nobody told us anything".
    """
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    detected = llm_backend.get_context_window(base_url, api_key) if base_url.strip() else None
    if detected is not None and detected > 0:
        return WindowInfo(max_tokens=int(detected), source="detected")
    configured = settings_store.get_llm(db).max_context_tokens
    if configured and configured > 0:
        return WindowInfo(max_tokens=int(configured), source="configured")
    return WindowInfo(
        max_tokens=max(1, get_settings().turn_context_fallback_window), source="fallback"
    )


def reserve_for(*parts: str) -> int:
    """Tokens the transcript may **not** use: everything else in the prompt, plus room to answer.

    ``parts`` are the non-transcript prompt pieces actually being sent (the output contract,
    the World Primer, stat guidance, retrieved lore, the direction). They are measured rather
    than estimated by a constant, because they vary by an order of magnitude between a bare
    scenario and a fully-authored world — a fixed reserve would either strand context in the
    first case or overflow in the second.

    ``TURN_CONTEXT_RESERVE_TOKENS`` is added on top as the answer allowance plus margin.
    """
    return sum(approx_tokens(p) for p in parts) + max(
        0, get_settings().turn_context_reserve_tokens
    )


def transcript_budget(window: WindowInfo, reserve: int, fraction: float | None = None) -> int:
    """Tokens the recent transcript may occupy.

    Capped at ``fraction`` of the whole window (default ``TURN_CONTEXT_MAX_FRACTION``, 0.5)
    even when more is nominally free. Filling a context window with transcript is not the
    same as using it well: the character prompt's tail is the act-now region, and burying it
    behind 100k tokens of history is how a model stops following the direction it was given.
    Never negative.
    """
    frac = get_settings().turn_context_max_fraction if fraction is None else fraction
    frac = min(max(frac, 0.0), 1.0)
    ceiling = int(window.max_tokens * frac)
    return max(0, min(ceiling, window.max_tokens - reserve))


def fit_window(
    beats: list[str], budget_tokens: int, block: int, *, current: int | None = None
) -> FitResult:
    """How many of the most recent ``beats`` fit in ``budget_tokens``.

    Walks newest→oldest accumulating :func:`approx_tokens`, then **quantises the depth down
    to a multiple of ``block``** so the window can only move in the steps
    ``buffer.anchored_turns`` already anchors to.

    ``current`` enables hysteresis: an existing window is kept unless the overage is at least
    a whole block. Without it a transcript hovering on the boundary would grow and shrink by
    one block every turn, and each change is a cold prefill — the exact cost the anchoring
    exists to avoid.
    """
    block = max(1, block)
    if not beats or budget_tokens <= 0:
        return FitResult(window_beats=0, dropped_beats=len(beats), used_tokens=0)

    used = 0
    fitting = 0
    for text in reversed(beats):
        cost = approx_tokens(text)
        if used + cost > budget_tokens and fitting > 0:
            break
        used += cost
        fitting += 1

    # Quantise DOWN, but never to zero while anything fits at all: a window of zero beats is
    # a scene with no memory, which is worse than one block of overage.
    depth = max(block, (fitting // block) * block) if fitting else 0
    depth = min(depth, len(beats))

    if current is not None and current > 0:
        kept = min(current, len(beats))
        # Compare against what ACTUALLY fits, not against the quantised depth. Quantising
        # first would read "39 beats fit, so the depth is 20" and shrink a 40-beat window by
        # a whole block because it is one beat over — the opposite of hysteresis.
        if fitting < kept and kept - fitting < block:
            depth = kept
        elif fitting > kept and fitting - kept < block:
            depth = kept

    used = sum(approx_tokens(t) for t in beats[-depth:]) if depth else 0
    return FitResult(
        window_beats=depth, dropped_beats=max(0, len(beats) - depth), used_tokens=used
    )

"""Stat values inside one play-through.

Kept separate from ``services/stats.py`` on purpose. That module is the **authoring**
surface — the storyline's stat schema and each character's authored baseline, edited from
the Library. This one is the **play** surface: what a stat is worth in *this* play-through.

Owner decision D-1 (2026-08-21). Before it, a value was global to a character, so two
play-throughs of one scenario shared a health value, a branch inherited whatever the last
one had done, and a rewind could only reconcile to whichever session was open.

Resolution order when play reads a stat:

1. the play-through's own row, if it has one;
2. else the character's authored starting value (:class:`CharacterStat`);
3. else the definition's ``default``.

``carry_over`` works in the **other** direction: when a play-through ends, a stat marked to
carry writes its value back onto the character, so the next scene opens where this one left
off. Anything not marked stays inside the play-through it happened in. That is why a branch
and a rewind are predictable — nothing leaks between play-throughs by accident — while an
authored starting value is still honoured.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.models import Character, CharacterStat, SessionCharacterStat, StatDefinition


def _definitions(db: Session, storyline_id: str) -> dict[str, StatDefinition]:
    return {
        d.key: d
        for d in db.scalars(
            select(StatDefinition).where(StatDefinition.storyline_id == storyline_id)
        )
    }


def baseline(db: Session, character_id: str) -> dict[str, int]:
    """The value every stat starts at for a **new** play-through of this character.

    This is the character's :class:`CharacterStat` row — the **authored** starting value,
    written by world population and edited in the Library — falling back to the definition's
    ``default`` where the character has none. It is deliberately *not* conditioned on
    ``carry_over``: an authored starting value is what the author said this character begins
    with, and a play-through that ignored it would open contradicting its own world.

    ``carry_over`` governs the other direction — see :func:`carry_forward`.

    Takes no session on purpose: a rewind replays from here, so it must be reproducible from
    authored data alone.
    """
    char = db.get(Character, character_id)
    if char is None:
        return {}
    defs = _definitions(db, char.storyline_id)
    carried = {
        row.key: row.value
        for row in db.scalars(
            select(CharacterStat).where(CharacterStat.character_id == character_id)
        )
    }
    out: dict[str, int] = {}
    for key, d in defs.items():
        if "character" not in (d.applies_to or ["character"]):
            continue
        out[key] = carried.get(key, d.default)
    return out


def carry_forward(db: Session, session_id: str) -> dict[str, int]:
    """Write this play-through's values back onto the characters, for stats that carry.

    This is what ``StatDefinition.carry_over`` means, and the only thing it means: when a
    play-through ends, a stat marked to carry updates the character's authored baseline, so
    the **next** scene opens where this one left off. A stat not marked to carry is scoped to
    the play-through it happened in and leaves no trace.

    Answers the long-open "stat lifecycle across scenarios" question in ``docs/checklist.md``
    per owner decision D-1: the default is **reset** (nothing carries unless it says so).

    Idempotent — it writes current values, so being called on every close is harmless.
    """
    rows = list(
        db.scalars(
            select(SessionCharacterStat).where(SessionCharacterStat.session_id == session_id)
        )
    )
    if not rows:
        return {}
    carried: dict[str, int] = {}
    by_char: dict[str, list[SessionCharacterStat]] = {}
    for row in rows:
        by_char.setdefault(row.character_id, []).append(row)
    for character_id, char_rows in by_char.items():
        char = db.get(Character, character_id)
        if char is None:
            continue
        defs = _definitions(db, char.storyline_id)
        existing = {
            r.key: r
            for r in db.scalars(
                select(CharacterStat).where(CharacterStat.character_id == character_id)
            )
        }
        for row in char_rows:
            d = defs.get(row.key)
            if d is None or not d.carry_over:
                continue
            if row.key in existing:
                existing[row.key].value = row.value
            else:
                db.add(
                    CharacterStat(
                        id=new_id("cs"),
                        character_id=character_id,
                        key=row.key,
                        value=row.value,
                    )
                )
            carried[f"{character_id}:{row.key}"] = row.value
    db.commit()
    return carried


def resolve(db: Session, session_id: str | None, character_id: str) -> dict[str, int]:
    """This character's stat values as they stand in this play-through.

    ``session_id`` of ``None`` means "no play-through yet" and yields the baseline, so the
    caller never has to special-case a scene that has not opened a session.
    """
    values = baseline(db, character_id)
    if not session_id:
        return values
    for row in db.scalars(
        select(SessionCharacterStat).where(
            SessionCharacterStat.session_id == session_id,
            SessionCharacterStat.character_id == character_id,
        )
    ):
        values[row.key] = row.value
    return values


def apply(
    db: Session, session_id: str, character_id: str, values: dict[str, int]
) -> dict[str, int]:
    """Write stat values for this play-through, clamped to each definition's range.

    Unknown keys are ignored rather than raising: this runs on the turn path, where the
    proposer is a language model and a bad key must cost a dropped change, not the turn.
    (The authoring path in ``stats.set_character_stats`` still raises — there, a bad key is
    a bug in the client.)
    """
    char = db.get(Character, character_id)
    if char is None:
        return {}
    defs = _definitions(db, char.storyline_id)
    existing = {
        row.key: row
        for row in db.scalars(
            select(SessionCharacterStat).where(
                SessionCharacterStat.session_id == session_id,
                SessionCharacterStat.character_id == character_id,
            )
        )
    }
    for key, raw in values.items():
        d = defs.get(key)
        if d is None:
            continue
        clamped = max(d.min, min(d.max, int(raw)))
        if key in existing:
            existing[key].value = clamped
        else:
            db.add(
                SessionCharacterStat(
                    id=new_id("scs"),
                    session_id=session_id,
                    character_id=character_id,
                    key=key,
                    value=clamped,
                )
            )
    db.commit()
    return resolve(db, session_id, character_id)


def copy(db: Session, source_session_id: str, target_session_id: str) -> int:
    """Copy a play-through's stat values onto another — the fork point of a branch.

    Without this a branch would start from the baseline while its copied transcript says
    otherwise, so the scene would open contradicting its own history.
    """
    rows = list(
        db.scalars(
            select(SessionCharacterStat).where(
                SessionCharacterStat.session_id == source_session_id
            )
        )
    )
    for row in rows:
        db.add(
            SessionCharacterStat(
                id=new_id("scs"),
                session_id=target_session_id,
                character_id=row.character_id,
                key=row.key,
                value=row.value,
            )
        )
    db.commit()
    return len(rows)


def clear(db: Session, session_id: str, character_ids: list[str] | None = None) -> int:
    """Drop a play-through's stat values, returning it to the baseline.

    The first half of a rewind: clear, then replay the surviving ``state_update`` events.
    """
    q = db.query(SessionCharacterStat).filter(SessionCharacterStat.session_id == session_id)
    if character_ids is not None:
        q = q.filter(SessionCharacterStat.character_id.in_(character_ids))
    removed = q.delete(synchronize_session=False)
    db.commit()
    return int(removed)

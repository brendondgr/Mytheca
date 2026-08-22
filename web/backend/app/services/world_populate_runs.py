"""Background world-build runs — a build that outlives the connection watching it.

A world build takes minutes: a roster, then a generation (often several) per character
and place, plus a render each when artwork is on. Streaming that straight out of the
request meant the *run itself* died with the socket — a dropped connection left a
half-built world, no way to watch the rest, and the client reporting "Lost the
connection while the server was still working."

So the run is a background thread with its own Session, appending **sequenced** frames
to an in-memory log. The HTTP stream is only a *view* of that log: it attaches, replays
from whatever sequence the client last saw, then follows live. A reconnect is therefore
lossless, and a client that goes away entirely does not stop the build.

Scope: in-process and non-durable. A backend restart still ends a run (the client then
reports it honestly). Runs are keyed by storyline, so re-requesting a build for a world
that is already building attaches to the run in flight rather than starting a second one
— a reconnect can never double-build.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import APIError
from app.schemas.world_populate import (
    PopulateDoneFrame,
    PopulateErrorFrame,
    PopulateEvent,
    WorldPopulateRequest,
)

# How long a finished run stays readable, so a client that reconnects just after the
# last frame still sees how it ended instead of a fresh (empty) run.
FINISHED_TTL_FRAMES = 1  # kept until a new run replaces it for the same storyline


@dataclass
class Run:
    """One world build: its frame log, and whether it is still going."""

    storyline_id: str
    frames: list[PopulateEvent] = field(default_factory=list)
    finished: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _tick: threading.Condition | None = None

    def __post_init__(self) -> None:
        self._tick = threading.Condition(self._lock)

    def append(self, frame: PopulateEvent) -> None:
        with self._lock:
            frame.seq = len(self.frames)
            self.frames.append(frame)
            self._tick.notify_all()

    def finish(self) -> None:
        with self._lock:
            self.finished = True
            self._tick.notify_all()

    def follow(self, from_seq: int = 0, poll: float = 0.5) -> Iterator[PopulateEvent]:
        """Replay from ``from_seq``, then follow live until the run finishes.

        The poll timeout is what lets the caller's keep-alive wrapper fill a long
        silent stretch (a single portrait render) with heartbeat frames.
        """
        cursor = max(0, from_seq)
        while True:
            with self._lock:
                while cursor >= len(self.frames) and not self.finished:
                    self._tick.wait(timeout=poll)
                    if cursor >= len(self.frames) and not self.finished:
                        break  # nothing new yet — let the caller emit a keep-alive
                pending = self.frames[cursor:]
                finished = self.finished
            for frame in pending:
                cursor += 1
                yield frame
            if finished and cursor >= len(self.frames):
                return


_runs: dict[str, Run] = {}
_registry_lock = threading.Lock()


def get_run(storyline_id: str) -> Run | None:
    with _registry_lock:
        return _runs.get(storyline_id)


def clear(storyline_id: str | None = None) -> None:
    """Drop a run (or all of them) — used by tests and by a fresh start."""
    with _registry_lock:
        if storyline_id is None:
            _runs.clear()
        else:
            _runs.pop(storyline_id, None)


def start_or_attach(
    db: Session,
    storyline_id: str,
    data: WorldPopulateRequest,
    populate: Callable[..., Iterator[PopulateEvent]],
) -> Run | None:
    """Resolve a request into the run it should watch.

    ``fromSeq > 0`` means *reconnect*: attach to this world's existing run — even a
    finished one, so a client that reconnects after the last frame still reads how it
    ended. It must never start a build, or a dropped connection would silently build
    the world a second time (a real failure this caught: a resume after completion
    produced four characters instead of two). ``None`` means there is nothing left to
    attach to — the process restarted — and the caller says so.

    ``fromSeq == 0`` is a fresh watch, which starts a build (or joins one in flight).
    """
    if data.from_seq > 0:
        return get_run(storyline_id)
    return start(db, storyline_id, data, populate)


def start(
    db: Session,
    storyline_id: str,
    data: WorldPopulateRequest,
    populate: Callable[..., Iterator[PopulateEvent]],
) -> Run:
    """Start a build for ``storyline_id``, or return the one already running.

    The worker gets its **own** Session bound to the same engine as the request's, so
    it never shares a Session across threads and tests exercise the real path against
    the same in-memory database.
    """
    with _registry_lock:
        existing = _runs.get(storyline_id)
        if existing is not None and not existing.finished:
            return existing
        run = Run(storyline_id=storyline_id)
        _runs[storyline_id] = run

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)

    def work() -> None:
        session = factory()
        try:
            for frame in populate(
                session,
                storyline_id,
                docs_overview=data.docs_overview,
                source=data.source,
                max_characters=data.max_characters,
                max_settings=data.max_settings,
                with_artwork=data.with_artwork,
                art_style=data.art_style,
            ):
                run.append(frame)
        except APIError as exc:
            run.append(PopulateErrorFrame(message=exc.message, fatal=True))
        except Exception:  # never leak a stack trace into the stream
            run.append(
                PopulateErrorFrame(message="Populating the world failed unexpectedly.", fatal=True)
            )
        finally:
            # A run that produced no terminal frame still has to end decisively, or a
            # watching client would wait forever on a build that is over.
            if not any(isinstance(f, PopulateDoneFrame) for f in run.frames) and not any(
                isinstance(f, PopulateErrorFrame) and f.fatal for f in run.frames
            ):
                run.append(PopulateErrorFrame(message="The build ended early.", fatal=True))
            session.close()
            run.finish()

    threading.Thread(target=work, name=f"world-build-{storyline_id}", daemon=True).start()
    return run

"""Background world-build runs — the build must outlive the connection watching it.

The reported failure: a ten-minute build streamed straight out of the request, so a
dropped socket ended the run and left a half-built world with no way to watch the rest.
These tests pin the properties that fix it — the run keeps going without a reader, a
reconnect replays exactly what it missed, and asking twice never builds twice.
"""

from __future__ import annotations

import threading

import pytest

from app.core.errors import APIError
from app.schemas.storyline import StorylineCreate
from app.schemas.world_populate import (
    PopulateDoneFrame,
    PopulateErrorFrame,
    PopulateStatusFrame,
    WorldPopulateRequest,
)
from app.services import crud, world_populate_runs


@pytest.fixture(autouse=True)
def _clean_registry():
    world_populate_runs.clear()
    yield
    world_populate_runs.clear()


@pytest.fixture
def world(db_session):
    return crud.create_storyline(
        db_session, StorylineCreate(id="embergate", title="Embergate", genre="Maritime")
    ).id


def _drain(run, from_seq: int = 0, limit: int | None = None) -> list:
    out = []
    for frame in run.follow(from_seq, poll=0.01):
        out.append(frame)
        if limit is not None and len(out) >= limit:
            break
    return out


def _await(run, timeout: float = 5.0) -> None:
    waited = 0.0
    while not run.finished and waited < timeout:
        threading.Event().wait(0.01)
        waited += 0.01
    assert run.finished, "the run never finished"


def test_frames_are_sequenced_and_replayable(db_session, world):
    def populate(session, storyline_id, **kwargs):
        yield PopulateStatusFrame(stage="roster", message="Planning…")
        yield PopulateStatusFrame(stage="character", message="Writing…")
        yield PopulateDoneFrame(characters=1, settings=0)

    run = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(run)

    assert [f.seq for f in run.frames] == [0, 1, 2]
    # A reader that saw the first two frames resumes with only what it missed.
    assert [f.seq for f in _drain(run, from_seq=2)] == [2]
    # …and one that saw nothing gets the whole run back.
    assert len(_drain(run)) == 3


def test_the_build_keeps_going_with_nobody_watching(db_session, world):
    """The run is the work; the stream is only a view of it."""
    written: list[str] = []

    def populate(session, storyline_id, **kwargs):
        written.append("started")
        yield PopulateStatusFrame(stage="roster", message="Planning…")
        written.append("finished")
        yield PopulateDoneFrame(characters=1, settings=0)

    run = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(run)

    assert written == ["started", "finished"]  # no reader ever attached
    assert isinstance(run.frames[-1], PopulateDoneFrame)


def test_asking_twice_attaches_instead_of_building_twice(db_session, world):
    """A reconnect must never start a second build for the same world."""
    starts: list[int] = []
    release = threading.Event()

    def populate(session, storyline_id, **kwargs):
        starts.append(1)
        release.wait(timeout=5)
        yield PopulateDoneFrame(characters=0, settings=0)

    first = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    second = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    release.set()
    _await(first)

    assert first is second
    assert starts == [1]


def test_a_finished_run_is_replaced_by_the_next_build(db_session, world):
    def populate(session, storyline_id, **kwargs):
        yield PopulateDoneFrame(characters=0, settings=0)

    first = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(first)
    second = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(second)

    assert first is not second


def test_a_fatal_error_ends_the_run_in_band(db_session, world):
    def populate(session, storyline_id, **kwargs):
        raise APIError(400, "bad_request", "Choose a model in Options first.")
        yield  # pragma: no cover - generator marker

    run = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(run)

    last = run.frames[-1]
    assert isinstance(last, PopulateErrorFrame) and last.fatal
    assert last.message == "Choose a model in Options first."


def test_an_unexpected_failure_never_leaks_a_stack_trace(db_session, world):
    def populate(session, storyline_id, **kwargs):
        raise RuntimeError("psycopg2.OperationalError: everything is on fire")
        yield  # pragma: no cover - generator marker

    run = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(run)

    last = run.frames[-1]
    assert isinstance(last, PopulateErrorFrame) and last.fatal
    assert "fire" not in last.message


def test_a_run_that_just_stops_still_ends_decisively(db_session, world):
    """Otherwise a watching client waits forever on a build that is already over."""

    def populate(session, storyline_id, **kwargs):
        yield PopulateStatusFrame(stage="roster", message="Planning…")

    run = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(run)

    last = run.frames[-1]
    assert isinstance(last, PopulateErrorFrame) and last.fatal
    assert _drain(run)[-1] is last  # a follower is released, not left hanging


def test_the_worker_uses_its_own_session(db_session, world):
    """A background thread must never share the request's Session."""
    seen: list[object] = []

    def populate(session, storyline_id, **kwargs):
        seen.append(session)
        # It is a real, usable session on the same database.
        assert crud.get_storyline(session, storyline_id).title == "Embergate"
        yield PopulateDoneFrame(characters=0, settings=0)

    run = world_populate_runs.start(db_session, world, WorldPopulateRequest(), populate)
    _await(run)

    assert seen and seen[0] is not db_session


def test_a_resume_never_starts_a_build(db_session, world):
    """A dropped connection must not build the world a second time."""
    starts: list[int] = []

    def populate(session, storyline_id, **kwargs):
        starts.append(1)
        yield PopulateDoneFrame(characters=1, settings=0)

    first = world_populate_runs.start_or_attach(
        db_session, world, WorldPopulateRequest(), populate
    )
    _await(first)

    resumed = world_populate_runs.start_or_attach(
        db_session, world, WorldPopulateRequest(from_seq=1), populate
    )

    assert resumed is first
    assert starts == [1]


def test_a_resume_with_no_run_left_attaches_to_nothing(db_session, world):
    """The process restarted: the caller reports that, rather than rebuilding."""

    def populate(session, storyline_id, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("a resume must never start a build")
        yield

    assert (
        world_populate_runs.start_or_attach(
            db_session, world, WorldPopulateRequest(from_seq=3), populate
        )
        is None
    )

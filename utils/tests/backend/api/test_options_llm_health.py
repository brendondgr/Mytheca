"""GET /options/llm/health — is the configured model actually there?

Four states, not a boolean, because they are four different problems with four different
fixes. In particular an endpoint that is **up while the model is absent** produces exactly the
same silence as one that is down, and telling them apart is the whole point: one is a typo in
Options, the other is a dead process.

Without this a player on a local model learns their endpoint died by sending a turn and waiting
out `LLM_GEN_TIMEOUT_SECONDS` — five minutes to be told nothing.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import llm, llm_backend


@pytest.fixture(autouse=True)
def _fresh_cache():
    """The probe is TTL-cached; a stale entry would make these test each other."""
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, handler):
    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _models(*ids: str):
    def handler(request: httpx.Request) -> httpx.Response:
        # Path-aware: the backend detection probes /version and /props first, and a handler
        # that answers everything the same way makes these tests pass or fail depending on
        # what ran before them (the repo's known engine-probe flake).
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": i} for i in ids]})
        return httpx.Response(404)

    return handler


def _configure(client, *, model: str = "test-model", base: str = "http://localhost:7070/v1"):
    client.patch(
        "/api/options/llm", json={"baseUrl": base, "model": model, "apiKey": "sk-test"}
    )


def test_a_served_model_is_reachable(client, monkeypatch):
    _configure(client)
    _patch(monkeypatch, _models("test-model", "other"))
    body = client.get("/api/options/llm/health").json()
    assert body["state"] == "reachable"
    assert body["model"] == "test-model"
    assert body["checkedAt"]
    assert "test-model" in body["detail"]


def test_an_endpoint_that_does_not_serve_the_model_is_not_merely_reachable(
    client, monkeypatch
):
    """The distinction that matters. The endpoint is fine; the *setting* is wrong, and a
    green light here would send the player looking at the wrong thing."""
    _configure(client, model="typo-model")
    _patch(monkeypatch, _models("test-model", "other"))
    body = client.get("/api/options/llm/health").json()
    assert body["state"] == "model_missing"
    assert "typo-model" in body["detail"]


def test_a_dead_endpoint_is_unreachable(client, monkeypatch):
    _configure(client)

    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patch(monkeypatch, dead)
    body = client.get("/api/options/llm/health").json()
    assert body["state"] == "unreachable"
    assert body["detail"]


def test_an_error_status_is_unreachable_not_reachable(client, monkeypatch):
    """A relay answering 503 "no healthy upstream" is up in the TCP sense and useless in
    every other one — observed live on this project's own endpoint."""
    _configure(client)

    def five_oh_three(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "no healthy upstream endpoint"})

    _patch(monkeypatch, five_oh_three)
    body = client.get("/api/options/llm/health").json()
    assert body["state"] == "unreachable"
    assert "503" in body["detail"]


def test_no_endpoint_configured_says_so_rather_than_reporting_a_failure(client, monkeypatch):
    """"You have not set this up" is a different message from "your model is down", and only
    one of them is alarming."""
    client.patch("/api/options/llm", json={"baseUrl": "", "model": "", "apiKey": ""})

    def never(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("nothing should be probed with no endpoint set")

    _patch(monkeypatch, never)
    assert client.get("/api/options/llm/health").json()["state"] == "unconfigured"


def test_a_configured_endpoint_with_no_model_is_also_unconfigured(client, monkeypatch):
    _configure(client, model="")

    def never(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("nothing should be probed with no model set")

    _patch(monkeypatch, never)
    assert client.get("/api/options/llm/health").json()["state"] == "unconfigured"


def test_an_endpoint_listing_nothing_is_reachable_not_missing(client, monkeypatch):
    """A relay that lists no models is not evidence the model is absent — claiming otherwise
    would send the player to fix a setting that is correct."""
    _configure(client)
    _patch(monkeypatch, _models())
    body = client.get("/api/options/llm/health").json()
    assert body["state"] == "reachable"


def test_the_probe_is_cached_rather_than_run_per_request(client, monkeypatch):
    """It is polled from the header every minute; an uncached probe would be a request per
    poll per open tab."""
    _configure(client)
    calls = {"n": 0}

    def counting(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            calls["n"] += 1
            return httpx.Response(200, json={"data": [{"id": "test-model"}]})
        return httpx.Response(404)

    _patch(monkeypatch, counting)
    client.get("/api/options/llm/health")
    first = calls["n"]
    client.get("/api/options/llm/health")
    assert calls["n"] == first, "the health probe was not cached"


def test_it_never_raises_whatever_the_endpoint_returns(client, monkeypatch):
    _configure(client)

    def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    _patch(monkeypatch, garbage)
    assert client.get("/api/options/llm/health").status_code == 200

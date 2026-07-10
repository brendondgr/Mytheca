"""Agentic storyline apply endpoint — the implement half, at the route level."""

from __future__ import annotations

from app.schemas.storyline_edit import FIELD_CATALOG


def _scope_body(writable: set[str]) -> dict:
    return {s.key: {"writable": s.key in writable, "readable": True} for s in FIELD_CATALOG}


def test_apply_updates_a_scoped_field(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/apply",
        json={
            "scope": _scope_body({"tagline"}),
            "plan": {"changes": [{"field": "tagline", "after": "Every secret has a price."}]},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["storyline"]["tagline"] == "Every secret has a price."
    assert body["applied"] == ["Updated tagline"]
    # persisted
    assert client.get(f"/api/storylines/{storyline_id}").json()["tagline"] == "Every secret has a price."


def test_apply_rejects_out_of_scope(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/apply",
        json={
            "scope": _scope_body({"tagline"}),
            "plan": {"changes": [{"field": "premise", "after": "sneaky"}]},
        },
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "scope_violation"


def test_apply_stale_base_version_conflicts(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/apply",
        json={
            "scope": _scope_body({"tagline"}),
            "plan": {"changes": [{"field": "tagline", "after": "New"}]},
            "baseVersion": "not-the-current-hash",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "stale_storyline"


def test_apply_adds_a_stat_through_validation(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/apply",
        json={
            "scope": _scope_body({"statistics"}),
            "plan": {
                "statChanges": [
                    {
                        "key": "resolve",
                        "changeType": "add",
                        "after": {"key": "resolve", "displayName": "Resolve", "min": 0, "max": 80, "default": 10},
                    }
                ]
            },
        },
    )
    assert res.status_code == 200
    defs = client.get(f"/api/storylines/{storyline_id}/stats").json()
    assert [d["key"] for d in defs] == ["resolve"]
    assert defs[0]["max"] == 80


def test_apply_missing_storyline_404(client):
    res = client.post(
        "/api/storylines/nope/agent/apply",
        json={"scope": _scope_body({"tagline"}), "plan": {"changes": [{"field": "tagline", "after": "x"}]}},
    )
    assert res.status_code == 404

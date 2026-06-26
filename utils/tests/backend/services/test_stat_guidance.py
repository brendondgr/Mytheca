"""Stat guidance loader — unit tests (fully offline).

Verifies:
- Each seeded guidance path (stats/health.md etc.) loads non-empty text.
- None/empty path → None.
- Unknown path → None.
- Path traversal attempts (``../core/config.py``, absolute like ``/etc/passwd``)
  → None (security).
- guidance_for() delegates to load_guidance() via the definition's .guidance field.

The module-level cache is cleared before each test via the _clear_cache() helper
so tests are independent of execution order.
"""

from __future__ import annotations

import pytest

from app.services import stat_guidance


@pytest.fixture(autouse=True)
def _clear_guidance_cache():
    """Reset the module cache before each test for isolation."""
    stat_guidance._clear_cache()
    yield
    stat_guidance._clear_cache()


# ---------------------------------------------------------------------------
# Seeded paths load non-empty text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "stats/health.md",
        "stats/suspicion.md",
        "stats/trust.md",
        "stats/patience.md",
    ],
)
def test_seeded_guidance_loads_non_empty_text(path: str):
    text = stat_guidance.load_guidance(path)
    assert text is not None, f"Expected text for {path}, got None"
    assert len(text) > 20, f"Expected substantive text for {path}, got: {text!r}"


# ---------------------------------------------------------------------------
# Empty / None input
# ---------------------------------------------------------------------------


def test_none_path_returns_none():
    assert stat_guidance.load_guidance(None) is None


def test_empty_string_returns_none():
    assert stat_guidance.load_guidance("") is None


def test_whitespace_only_path_returns_none():
    # An all-whitespace path is falsy after strip — treated as empty.
    assert stat_guidance.load_guidance("   ") is None


# ---------------------------------------------------------------------------
# Unknown (non-existent) path
# ---------------------------------------------------------------------------


def test_unknown_path_returns_none():
    assert stat_guidance.load_guidance("stats/does_not_exist.md") is None


def test_completely_unknown_path_returns_none():
    assert stat_guidance.load_guidance("no/such/file.md") is None


# ---------------------------------------------------------------------------
# Security: traversal and absolute paths → None
# ---------------------------------------------------------------------------


def test_traversal_path_returns_none():
    """``../core/config.py`` must never be readable."""
    assert stat_guidance.load_guidance("../core/config.py") is None


def test_deep_traversal_path_returns_none():
    assert stat_guidance.load_guidance("stats/../../core/config.py") is None


def test_absolute_path_returns_none():
    assert stat_guidance.load_guidance("/etc/passwd") is None


def test_absolute_path_to_real_file_returns_none(tmp_path):
    """An absolute path to a real file must still be rejected."""
    real_file = tmp_path / "secret.md"
    real_file.write_text("secret content")
    assert stat_guidance.load_guidance(str(real_file)) is None


# ---------------------------------------------------------------------------
# guidance_for() delegation
# ---------------------------------------------------------------------------


class _FakeDef:
    """Minimal stand-in for a StatDefinition."""

    def __init__(self, guidance: str | None):
        self.guidance = guidance


def test_guidance_for_with_valid_path():
    d = _FakeDef("stats/health.md")
    text = stat_guidance.guidance_for(d)
    assert text is not None
    assert "Health" in text


def test_guidance_for_with_none_guidance():
    d = _FakeDef(None)
    assert stat_guidance.guidance_for(d) is None


def test_guidance_for_with_traversal_guidance():
    d = _FakeDef("../core/config.py")
    assert stat_guidance.guidance_for(d) is None


# ---------------------------------------------------------------------------
# Cache: second call returns cached result without re-reading
# ---------------------------------------------------------------------------


def test_load_guidance_is_cached(monkeypatch, tmp_path):
    """load_guidance returns the cached value without hitting the filesystem twice."""
    calls: list[str] = []

    original_content_dir = stat_guidance._content_dir

    def patched_content_dir():
        return original_content_dir()

    # Patch Path.read_text on the resolved file to count reads.
    import pathlib

    original_read_text = pathlib.Path.read_text

    def counting_read_text(self, *args, **kwargs):
        calls.append(str(self))
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", counting_read_text)

    # First call: reads the file.
    result1 = stat_guidance.load_guidance("stats/health.md")
    # Second call: should return from cache without reading the file again.
    result2 = stat_guidance.load_guidance("stats/health.md")

    assert result1 == result2
    health_reads = [c for c in calls if "health.md" in c]
    assert len(health_reads) == 1, "File should be read exactly once (cached thereafter)"

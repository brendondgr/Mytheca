"""Stat guidance loader.

Reads per-stat Markdown guidance files from the authored content package
(``app/content/stats/``). Results are cached in a module-level dict so each
file is read at most once per process lifetime.

Security: only paths that stay inside ``content_dir`` are allowed — absolute
paths and any component containing ``..`` are rejected (return None).
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings

# Module-level cache: relative path string → loaded text (or None if absent/rejected).
_cache: dict[str, str | None] = {}


def _content_dir() -> Path:
    """Return the content package directory from settings."""
    return get_settings().content_dir


def load_guidance(path: str | None) -> str | None:
    """Load a guidance Markdown file by its relative path (e.g. ``stats/health.md``).

    Returns None when:
    - ``path`` is falsy,
    - the path is absolute,
    - any component of the path contains ``..``,
    - the resolved file escapes ``content_dir`` (belt-and-suspenders),
    - the file does not exist.

    Results are cached by relative path so each file is read at most once.
    """
    if not path:
        return None

    # Cache hit (including cached None for missing/rejected paths).
    if path in _cache:
        return _cache[path]

    # Reject absolute paths.
    if Path(path).is_absolute():
        _cache[path] = None
        return None

    # Reject traversal components.
    parts = Path(path).parts
    if any(part == ".." for part in parts):
        _cache[path] = None
        return None

    content_dir = _content_dir()
    resolved = (content_dir / path).resolve()

    # Belt-and-suspenders: ensure the resolved path is still inside content_dir.
    try:
        resolved.relative_to(content_dir.resolve())
    except ValueError:
        _cache[path] = None
        return None

    if not resolved.is_file():
        _cache[path] = None
        return None

    text = resolved.read_text(encoding="utf-8").strip() or None
    _cache[path] = text
    return text


def guidance_for(definition) -> str | None:
    """Return loaded guidance text for a ``StatDefinition``, or None."""
    return load_guidance(getattr(definition, "guidance", None))


def _clear_cache() -> None:
    """Clear the module-level guidance cache (for tests)."""
    _cache.clear()

"""Application settings.

Single source of runtime configuration for the backend. Values come from the
process environment (and the repo-root ``.env`` in development); every variable
is documented in ``.env.example``. See ``docs/architecture.md`` for the data
layer and ``docs/workflow.md`` for the environment rules.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = three parents up from this file (web/backend/app/core/config.py).
REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Typed view over the environment. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    app_env: str = "development"
    secret_key: str = "change-me"

    # CORS — the frontend dev origin allowed to call the API.
    frontend_origin: str = "http://localhost:3346"

    # Core data stores.
    database_url: str = "postgresql+psycopg://velora:velora@localhost:3347/velora"
    redis_url: str = "redis://localhost:3348/0"

    # --- Turn loop (the runtime story engine) ---
    # The recent-turn buffer + per-character interior state live in Redis; like the
    # Neo4j/Qdrant seams the engine is best-effort (Redis down → no buffer/interior,
    # the turn still runs and persists to Postgres). Blank ``REDIS_URL`` disables it.
    # ``turn_buffer_size`` caps the recent-turn buffer; ``turn_max_concurrency``
    # bounds the off-hot-path / independent worker pool (sequential speech stays
    # sequential regardless). ``turn_reflection_enabled`` toggles the read-time
    # reflection interlude (per-character interior state). ``turn_ttft_slo_ms`` is an
    # informational time-to-first-token target the concurrency hardening logs against.
    turn_buffer_size: int = 12
    turn_max_concurrency: int = 4
    turn_reflection_enabled: bool = True
    turn_ttft_slo_ms: int = 1200

    # The Story Graph substrate (Neo4j). The container is owned by ``app.py`` like
    # Postgres/Redis; the driver connects lazily (on scenario load / character &
    # setting writes) and degrades gracefully when unset/unreachable. Bolt is
    # published on host port 3349 (HTTP browser on 3350) so Velora coexists with
    # any Neo4j already on 7687/7474. See ``app/core/neo4j.py``.
    neo4j_uri: str = "bolt://localhost:3349"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "velora-graph"

    # AI provider selection (the provider-agnostic interface lands in a later phase).
    llm_provider: str = "openai"
    openai_api_key: str = ""
    local_llm_base_url: str = "http://localhost:11434"

    # Inference-engine auto-detection (vLLM vs. llama.cpp), used to carry the
    # backend-controlled reasoning/thinking budget under the engine's request key.
    # The detection is cached for ``cache_ttl`` seconds and a background poller
    # re-probes the configured endpoint every ``poll`` seconds so the server adapts
    # when the operator swaps engines. See ``app/services/llm_backend.py``.
    llm_backend_poll_seconds: int = 30
    llm_backend_cache_ttl_seconds: int = 60

    # ComfyUI image generation — a local Comfy server (HTTP + WebSocket protocol).
    comfyui_base_url: str = "http://localhost:8199"

    # --- RAG: embeddings (fastembed/bge-large, CPU-default, no torch) ---
    # ``embed_provider``: "fastembed" (real ONNX model) or "hash" (the deterministic
    # offline fallback the test suite forces; see utils/tests/backend/conftest.py).
    embed_provider: str = "fastembed"
    embed_model: str = "BAAI/bge-large-en-v1.5"
    embed_dim: int = 1024
    # Execution device: "cpu" (default), "cuda" (needs onnxruntime-gpu), or "rocm".
    # Unavailable accelerators fall back to CPU inside onnxruntime (best-effort).
    embed_device: str = "cpu"
    # Where fastembed caches downloaded ONNX models (defaults to its own cache).
    embed_cache_dir: str = ""

    # --- RAG: vector store (Qdrant) ---
    # The container is owned by ``app.py`` like Postgres/Redis/Neo4j; the client
    # connects lazily and degrades gracefully when unset/unreachable (CRUD and the
    # test suite run with no Qdrant). Blank disables the vector store entirely.
    qdrant_url: str = "http://localhost:3351"
    qdrant_collection: str = "velora_lore"

    # Generated media (character portraits, etc.), served read-only at ``/media``.
    media_dir: Path = REPO_ROOT / "media"

    @property
    def comfyui_workflows_dir(self) -> Path:
        """Directory holding saved ComfyUI workflow JSON (e.g. ZiT-Workflow.json)."""
        return REPO_ROOT / "utils" / "workflows"

    @property
    def content_dir(self) -> Path:
        """Directory holding the authored content package (Markdown guidance, etc.)."""
        return Path(__file__).resolve().parents[1] / "content"

    @property
    def portraits_dir(self) -> Path:
        """Directory holding generated character portraits (WebP)."""
        return self.media_dir / "portraits"

    @property
    def scenes_dir(self) -> Path:
        """Directory holding generated setting/scene establishing images (WebP)."""
        return self.media_dir / "scenes"

    @property
    def is_sqlite(self) -> bool:
        """True when pointed at SQLite (used by tests and the engine factory)."""
        return self.database_url.startswith("sqlite")

    @property
    def redis_configured(self) -> bool:
        """True when a Redis URL is set (the live turn buffer / interior state is in play).

        Best-effort like the Neo4j/Qdrant seams: when false the buffer/interior
        helpers no-op so CRUD and the test suite run with no Redis.
        """
        return bool(self.redis_url.strip())

    @property
    def neo4j_configured(self) -> bool:
        """True when a Neo4j URI is set (the Story Graph substrate is in play).

        Graph sync is best-effort: when this is false the writer/reader no-op so
        CRUD and the test suite run with no Neo4j (see ``app/core/neo4j.py``).
        """
        return bool(self.neo4j_uri.strip())

    @property
    def qdrant_configured(self) -> bool:
        """True when a Qdrant URL is set (the vector store is in play).

        Like the Neo4j seam, retrieval is best-effort: when false the store/indexer
        no-op so CRUD and the test suite run with no Qdrant (see app/core/qdrant.py).
        """
        return bool(self.qdrant_url.strip())

    @property
    def cors_origins(self) -> list[str]:
        """Allowed CORS origins.

        ``FRONTEND_ORIGIN`` may be a comma-separated list. The localhost/127.0.0.1
        counterpart of each origin is added automatically, since the dev server is
        reachable under both hostnames.
        """
        raw = [o.strip() for o in self.frontend_origin.split(",") if o.strip()]
        origins = set(raw)
        for origin in raw:
            if "localhost" in origin:
                origins.add(origin.replace("localhost", "127.0.0.1"))
            elif "127.0.0.1" in origin:
                origins.add(origin.replace("127.0.0.1", "localhost"))
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance (loaded once per process)."""
    return Settings()

"""Token-budget guard (brief §2 "Token budget guard").

BGE truncates at 512 tokens, so a long entry body would silently drop its tail
from the dense vector. We avoid loading the model tokenizer here (Phase 1 is
dependency-free) and approximate tokens by characters; the real fastembed
embedder still truncates internally, so this guard only decides *what* to feed
the dense vector — header+summary always survive, the body is trimmed to fit.
"""

from __future__ import annotations

from app.rag.const import EMBED_MAX_TOK

# Rough chars-per-token for English prose; matches the frontend budget heuristic
# (lib/contextBudget.ts CHARS_PER_TOKEN) so both sides estimate the same way.
CHARS_PER_TOKEN = 4


def approx_tokens(text: str) -> int:
    """Approximate token count of ``text`` (chars / 4, rounded up)."""
    if not text:
        return 0
    return -(-len(text) // CHARS_PER_TOKEN)  # ceil division


def fit_to_budget(head: str, body: str, max_tokens: int = EMBED_MAX_TOK) -> str:
    """Return ``head`` plus as much of ``body`` as fits ``max_tokens``.

    ``head`` (the front-matter header + summary) is never dropped; the body is
    truncated on a whitespace boundary so the dense vector stays anchored on the
    metadata and summary even for long entries.
    """
    budget_chars = max_tokens * CHARS_PER_TOKEN
    head = head.strip()
    body = body.strip()
    if not body:
        return head
    joined = f"{head}\n\n{body}" if head else body
    if len(joined) <= budget_chars:
        return joined
    remaining = budget_chars - len(head) - 2  # 2 for the "\n\n" separator
    if remaining <= 0:
        return head
    clipped = body[:remaining]
    cut = clipped.rfind(" ")
    if cut > remaining // 2:  # only honor a word boundary if it isn't pathological
        clipped = clipped[:cut]
    return f"{head}\n\n{clipped}".strip()

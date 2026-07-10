"""Agentic storyline editor/creator — a conversational, scope-aware, plan→implement agent.

Modules:
- ``scope``   — write/read scope helpers, the dynamic response-schema builder, the diff guard.
- ``core``    — the shared conversation engine (assemble → prompt → LLM → parse → frames).
- ``editor``  — ``storyline_editor_agent`` (existing storyline, surgical edits).
- ``creation``— ``storyline_creation_agent`` (blank/partial start, generative breadth).
"""

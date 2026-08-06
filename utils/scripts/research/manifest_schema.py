"""Pydantic model of the experiment manifest contract.

Mirrors ``docs/research/AGENT_INSTRUCTIONS.md`` §3.1. Every field the contract calls
mandatory is required here; fields the contract marks optional are nullable.

The model is deliberately permissive about *values* and strict about *shape*. A
back-filled experiment is allowed to say ``commit: unknown``; it is not allowed to
omit the ``code`` block, because an omitted block reads as "not applicable" while an
explicit ``unknown`` reads as "we could not recover this". The contract's §9.3 makes
that distinction load-bearing.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Status(str, Enum):
    """Lifecycle of an experiment. `failed` and `superseded` folders are never
    deleted — see the contract §3.4."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class _Block(BaseModel):
    """Base for manifest sub-blocks. Unknown keys are rejected so a typo in a field
    name fails loudly instead of silently recording nothing."""

    model_config = ConfigDict(extra="forbid")


class CodeBlock(_Block):
    commit: str
    branch: str
    entrypoint: str
    dirty: bool


class ConfigBlock(_Block):
    path: str | None = None
    hash: str | None = None


class DataBlock(_Block):
    name: str
    version: str
    split: str | None = None
    n_examples: int = 0
    dvc_path: str | None = None
    hash: str | None = None


class EnvironmentBlock(_Block):
    python: str
    lockfile: str | None = None
    container: str | None = None


class ComputeBlock(_Block):
    hardware: str
    wall_clock_hours: float = 0.0
    estimated_cost_usd: float = 0.0


class LlmBlock(_Block):
    model: str
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    prompt_files: list[str] = Field(default_factory=list)
    prompt_hash: str | None = None
    tool_schema_hash: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    nondeterminism_note: str | None = None


class MetricValue(_Block):
    """A metric is a distribution over runs, never a single number.

    ``n`` is required precisely so that an excluded seed cannot be hidden: if a run
    crashed, this cell says ``n: 4`` and ``ISSUES.md`` says why.
    """

    mean: float
    std: float | None = None
    n: int


class MetricsBlock(_Block):
    primary: str | None = None
    values: dict[str, MetricValue] = Field(default_factory=dict)


class Manifest(BaseModel):
    """The full manifest. Validation of *cross-field* rules (a complete experiment
    with no metrics, a primary metric absent from values) lives here; validation of
    rules that need the filesystem or CLAIMS.md lives in ``validate_research.py``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    slug: str
    title: str
    status: Status
    date_started: Any
    date_completed: Any | None = None
    authors: list[str] = Field(default_factory=list)

    purpose: str
    hypothesis: str

    code: CodeBlock
    config: ConfigBlock
    data: DataBlock
    seeds: list[int] = Field(default_factory=list)
    n_runs: int = 0
    environment: EnvironmentBlock
    compute: ComputeBlock

    llm: LlmBlock | None = None

    metrics: MetricsBlock
    baselines_compared: list[str] = Field(default_factory=list)
    statistical_test: str | None = None

    supports_claims: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    supersedes: str | None = None
    superseded_by: str | None = None
    related: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        parts = v.split("-")
        if len(parts) != 4 or parts[0] != "EXP":
            raise ValueError(f"id must look like EXP-YYYY-MM-NNN, got {v!r}")
        year, month, seq = parts[1:]
        if not (len(year) == 4 and year.isdigit()):
            raise ValueError(f"id year must be 4 digits, got {year!r}")
        if not (len(month) == 2 and month.isdigit() and 1 <= int(month) <= 12):
            raise ValueError(f"id month must be 01-12, got {month!r}")
        if not (len(seq) == 3 and seq.isdigit()):
            raise ValueError(f"id sequence must be 3 digits, got {seq!r}")
        return v

    def cross_field_errors(self) -> list[str]:
        """Rules that need more than one field. Returned rather than raised so the
        validator can report every problem in a folder at once."""
        errors: list[str] = []

        # The contract's §7.3 headline rule: a finished experiment with no numbers is
        # a finished experiment that recorded nothing.
        if self.status is Status.COMPLETE and not self.metrics.values:
            errors.append("status is 'complete' but metrics.values is empty")

        # `planned` and `failed` are explicitly allowed to have no metrics — a failed
        # run that is forced to invent numbers is worse than one that records none.
        if self.status is Status.COMPLETE and not self.metrics.primary:
            errors.append("status is 'complete' but metrics.primary is unset")

        if self.metrics.primary and self.metrics.values:
            if self.metrics.primary not in self.metrics.values:
                errors.append(
                    f"metrics.primary {self.metrics.primary!r} is not a key in metrics.values "
                    f"(have: {sorted(self.metrics.values)})"
                )

        if self.status in (Status.COMPLETE, Status.FAILED) and self.date_completed is None:
            errors.append(f"status is '{self.status.value}' but date_completed is null")

        if self.status is Status.SUPERSEDED and not self.superseded_by:
            errors.append("status is 'superseded' but superseded_by is null")

        for name, value in self.metrics.values.items():
            if value.n <= 0:
                errors.append(f"metric {name!r} has n={value.n}; a metric needs at least one run")
            # Single-run means have no spread to report, so std may legitimately be
            # null there and nowhere else.
            if value.n > 1 and value.std is None:
                errors.append(
                    f"metric {name!r} has n={value.n} but no std; "
                    "report mean +/- std across seeds, never a bare mean"
                )

        return errors

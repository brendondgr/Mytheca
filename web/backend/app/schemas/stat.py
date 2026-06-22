"""Stat schemas.

A stat *definition* lives on a storyline (range locked at creation). Character
stat *values* travel as a bare ``{key: value}`` map (dynamic keys, so no model /
no aliasing) — clamped to the definition's range by the service.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from app.schemas.base import CamelModel, Visibility


class StatDefinitionBase(CamelModel):
    key: str
    display_name: str
    description: str = ""
    min: int = 0
    max: int = 100
    default: int = 0
    visibility: Visibility = "public"
    guidance: str | None = None
    applies_to: list[str] = Field(default_factory=lambda: ["character"])


class StatDefinitionCreate(StatDefinitionBase):
    @model_validator(mode="after")
    def _check_range(self) -> StatDefinitionCreate:
        if self.min >= self.max:
            raise ValueError("min must be less than max")
        if not (self.min <= self.default <= self.max):
            raise ValueError("default must be within [min, max]")
        return self


class StatDefinitionUpdate(CamelModel):
    """Only descriptive fields are editable — the range is locked at creation."""

    display_name: str | None = None
    description: str | None = None
    guidance: str | None = None
    applies_to: list[str] | None = None


class StatDefinitionRead(StatDefinitionBase):
    pass


# Character stat values: a plain map, e.g. {"health": 80, "strength": 14}.
StatValues = dict[str, int]

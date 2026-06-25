"""Stat schemas.

A stat *definition* lives on a storyline (range locked at creation). Character
stat *values* travel as a bare ``{key: value}`` map (dynamic keys, so no model /
no aliasing) — clamped to the definition's range by the service.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from app.schemas.base import CamelModel, Visibility


class StatBand(CamelModel):
    """A labeled value band ("ticker") — what a range of a stat *means*.

    e.g. ``{min: 0, max: 20, label: "Nearly dead"}``. Used for future
    state-extraction: it lets the system name a character's condition from a
    number. Bands need not tile the full range or be contiguous.
    """

    min: int
    max: int
    label: str

    @model_validator(mode="after")
    def _check(self) -> StatBand:
        if self.min > self.max:
            raise ValueError("band min must be ≤ max")
        if not self.label.strip():
            raise ValueError("band label is required")
        return self


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
    bands: list[StatBand] = Field(default_factory=list)


class StatDefinitionCreate(StatDefinitionBase):
    @model_validator(mode="after")
    def _check_range(self) -> StatDefinitionCreate:
        if self.min >= self.max:
            raise ValueError("min must be less than max")
        if not (self.min <= self.default <= self.max):
            raise ValueError("default must be within [min, max]")
        return self


class StatDefinitionUpdate(CamelModel):
    """Stats are freely editable — name, description, range, bands.

    The range (``min``/``max``/``default``) is now editable; the service
    re-clamps existing character values when a range narrows. Only the ``key``
    is immutable (it identifies the stat across characters).
    """

    display_name: str | None = None
    description: str | None = None
    min: int | None = None
    max: int | None = None
    default: int | None = None
    visibility: Visibility | None = None
    guidance: str | None = None
    applies_to: list[str] | None = None
    bands: list[StatBand] | None = None


class StatDefinitionRead(StatDefinitionBase):
    pass


# Character stat values: a plain map, e.g. {"health": 80, "strength": 14}.
StatValues = dict[str, int]

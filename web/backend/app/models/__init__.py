"""SQLAlchemy models. Importing this package registers every table on ``Base``."""

from __future__ import annotations

from app.core.db import Base
from app.models.character import Character
from app.models.scenario import Scenario
from app.models.setting import Setting
from app.models.stat import CharacterStat, StatDefinition
from app.models.storyline import Storyline

__all__ = [
    "Base",
    "Storyline",
    "Character",
    "Setting",
    "Scenario",
    "StatDefinition",
    "CharacterStat",
]

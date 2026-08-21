"""ORM models: relations, JSON round-trip, uniqueness, and cascade delete."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Character,
    CharacterStat,
    Scenario,
    Setting,
    StatDefinition,
    Storyline,
)


def _embergate() -> Storyline:
    sl = Storyline(id="embergate", title="Embergate", genre="Maritime Intrigue")
    sl.characters.append(Character(id="maerin", name="Maerin Voss", mono="MV", position=0))
    sl.settings.append(
        Setting(id="saltworn", name="The Saltworn Tavern", type="Social Hub", desc="Lamplit.")
    )
    sl.scenarios.append(
        Scenario(
            id="embergate-sc",
            title="The Embergate Conspiracy",
            cast_ids=["maerin"],
            setting_id="saltworn",
            branches=[{"label": "Confront", "check": "Insight", "outcome": "x", "tag": "check_request"}],
        )
    )
    sl.stat_definitions.append(
        StatDefinition(key="health", display_name="Health", min=0, max=100, default=100)
    )
    return sl


def test_children_and_json_round_trip(db_session):
    db_session.add(_embergate())
    db_session.commit()

    sl = db_session.get(Storyline, "embergate")
    assert [c.name for c in sl.characters] == ["Maerin Voss"]
    sc = sl.scenarios[0]
    assert sc.cast_ids == ["maerin"]
    assert sc.setting_id == "saltworn"
    assert sc.branches[0]["tag"] == "check_request"  # JSON survived the round trip
    assert sl.stat_definitions[0].applies_to == ["character"]  # default callable


def test_stat_definition_unique_per_storyline(db_session):
    db_session.add(_embergate())
    db_session.commit()
    db_session.add(StatDefinition(storyline_id="embergate", key="health", display_name="Dup"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_character_stat_unique_per_character(db_session):
    db_session.add(_embergate())
    db_session.commit()
    db_session.add_all(
        [
            CharacterStat(character_id="maerin", key="health", value=80),
            CharacterStat(character_id="maerin", key="health", value=20),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_delete_storyline_cascades(db_session):
    db_session.add(_embergate())
    db_session.commit()
    db_session.add(CharacterStat(character_id="maerin", key="health", value=80))
    db_session.commit()

    db_session.delete(db_session.get(Storyline, "embergate"))
    db_session.commit()

    assert db_session.query(Character).count() == 0
    assert db_session.query(Setting).count() == 0
    assert db_session.query(Scenario).count() == 0
    assert db_session.query(StatDefinition).count() == 0
    assert db_session.query(CharacterStat).count() == 0  # via character cascade


def test_the_reconciler_quotes_a_string_default_for_postgres():
    """The preflight reconciler must render defaults the way the dialect would.

    It builds `ALTER TABLE ... ADD COLUMN` by hand, and it used to str() the server default
    straight into the DDL. `server_default="medium"` then became `DEFAULT medium`, which
    Postgres reads as a COLUMN REFERENCE and refuses ("cannot use column reference in DEFAULT
    expression"), taking preflight — and therefore the whole backend — down at boot.

    Numeric defaults ("14", "4") hid it, because a bare number is already a valid literal,
    and SQLite accepts either form. So 1,200 passing tests said nothing about it: the bug was
    only reachable by starting the real backend.

    This asserts the *mechanism* (the dialect compiler renders it) rather than one column, so
    the next string column with a default is covered without anyone remembering.
    """
    from sqlalchemy import Column, Integer, MetaData, String, Table
    from sqlalchemy.dialects import postgresql

    from app.core.bootstrap import add_column_ddl

    dialect = postgresql.dialect()
    probe = Table(
        "probe",
        MetaData(),
        # A BARE string default — the shape that broke, written the way it is easiest to
        # write. The DDL builder must quote it regardless of how the model spelled it.
        Column("tier", String, nullable=False, server_default="medium"),
        Column("count", Integer, nullable=False, server_default="14"),
        Column("note", String, nullable=True),
        Column("needs_backfill", String, nullable=False),
    )

    assert "DEFAULT 'medium'" in add_column_ddl(dialect, probe, probe.c.tier)
    assert "DEFAULT medium" not in add_column_ddl(dialect, probe, probe.c.tier)
    # A numeric default is quoted too (`DEFAULT '14'`). That is correct and not a
    # regression: Postgres coerces a string literal to the column's type, so an INTEGER
    # column takes '14' as 14. The pre-existing numeric columns keep working.
    assert add_column_ddl(dialect, probe, probe.c.count).endswith("NOT NULL DEFAULT '14'")
    # A nullable column needs no default at all...
    assert "DEFAULT" not in add_column_ddl(dialect, probe, probe.c.note)
    # ...and a NOT NULL column with nothing to backfill with is reported, not attempted.
    assert add_column_ddl(dialect, probe, probe.c.needs_backfill) is None


def test_every_string_server_default_renders_as_a_literal_on_postgres():
    """No model column may compile to a bare-identifier DEFAULT on Postgres."""
    import re

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.core.db import Base

    bad: list[str] = []
    for table in Base.metadata.tables.values():
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for line in ddl.splitlines():
            match = re.search(r"^\s*(\w+)\s+.*\bDEFAULT\s+([^\s,]+)", line)
            if not match:
                continue
            column, default = match.groups()
            # Numbers, quoted literals and function calls are all fine, and so are SQL's
            # own bare-word literals — `DEFAULT false` is a boolean, not an identifier.
            if re.fullmatch(r"[A-Za-z_]\w*", default) and default.lower() not in {
                "true", "false", "null", "current_timestamp", "current_date", "current_user",
            }:
                bad.append(f"{table.name}.{column} -> DEFAULT {default}")
    assert not bad, (
        "unquoted string server_default(s) — Postgres reads these as column references: "
        + ", ".join(bad)
    )

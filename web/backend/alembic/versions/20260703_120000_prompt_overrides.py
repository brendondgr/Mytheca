"""per-storyline / per-scenario writing-prompt overrides

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-03 12:00:00

Adds a nullable JSON ``prompt_overrides`` column to ``storylines`` and ``scenarios``
({registry key -> prompt text}). Nullable so it self-heals on already-migrated DBs via
``bootstrap._reconcile_additive_columns`` and needs no server-default backfill; the code
reads ``NULL`` as ``{}``.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import Text

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('storylines', 'scenarios'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'prompt_overrides',
                    sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'),
                    nullable=True,
                )
            )


def downgrade() -> None:
    for table in ('storylines', 'scenarios'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('prompt_overrides')

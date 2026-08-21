"""scenario per-scene beat length (beat_length)

How much a character says in one beat: short (1-2 paragraphs), medium (2-4, the default
and closest to prior behaviour), long (5-6). Existing rows read as ``medium`` via the
server default, so a scenario created before this migration plays exactly as it did.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-21 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('beat_length', sa.String(), nullable=False, server_default='medium')
        )


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('beat_length')

"""scenario-authored direction verbs

The direction row's one-tap verb bar ships with four built-in groups (Pace · Tone · Event ·
Exit). ``scenarios.direction_verbs`` lets a scene add its own, appended to their group after
the built-ins: ``[{"label", "group", "text"}]``, where ``label`` is the chip and ``text`` is
the phrasing written into the direction box for the player to edit.

Nullable, so every existing scenario reads as "no verbs of its own" and the bar renders
exactly as it does today.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-22 15:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('direction_verbs', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('direction_verbs')

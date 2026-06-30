"""setting scene art prompt columns

Revision ID: e7a8b9c0d1f2
Revises: d4f1a2b3c5e6
Create Date: 2026-06-29 12:05:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7a8b9c0d1f2'
down_revision: Union[str, None] = 'd4f1a2b3c5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scene_art_positive', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('scene_art_negative', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('scene_art_negative')
        batch_op.drop_column('scene_art_positive')

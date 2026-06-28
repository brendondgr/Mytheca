"""scenario scene art columns

Revision ID: e13f0f3faea0
Revises: b23834895e1c
Create Date: 2026-06-28 12:17:50

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e13f0f3faea0'
down_revision: Union[str, None] = 'b23834895e1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('scene_art_positive', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('scene_art_negative', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('scene_art_negative')
        batch_op.drop_column('scene_art_positive')
        batch_op.drop_column('image')

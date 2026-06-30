"""character portrait prompt columns

Revision ID: d4f1a2b3c5e6
Revises: c0a7d0c5e1f2
Create Date: 2026-06-29 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4f1a2b3c5e6'
down_revision: Union[str, None] = 'c0a7d0c5e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('portrait_positive', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('portrait_negative', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_column('portrait_negative')
        batch_op.drop_column('portrait_positive')

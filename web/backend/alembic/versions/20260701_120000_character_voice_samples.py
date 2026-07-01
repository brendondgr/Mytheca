"""character voice_samples column

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-01 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'voice_samples',
                sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_column('voice_samples')

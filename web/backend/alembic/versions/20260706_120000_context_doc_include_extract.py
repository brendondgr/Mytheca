"""context document include_extract (opt-in build extraction)

Adds the per-document opt-in flag that gates whether **Build the whole world**
mines a doc for named characters/settings. Additive + NOT NULL with a server
default of ``false`` so existing rows backfill and the additive-column reconciler
self-heals it (matching the established non-null-with-server-default pattern).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-06 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('context_documents', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'include_extract',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('context_documents', schema=None) as batch_op:
        batch_op.drop_column('include_extract')

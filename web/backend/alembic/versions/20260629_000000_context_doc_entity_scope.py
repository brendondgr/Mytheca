"""context document entity scope

Adds the optional entity scope to context_documents so a document can belong to a
specific character/setting/scenario (and reappear in that editor) instead of only
the storyline. Additive + nullable — coexists with the create_all reconciler.

Revision ID: c0a7d0c5e1f2
Revises: e13f0f3faea0
Create Date: 2026-06-29 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c0a7d0c5e1f2'
down_revision: Union[str, None] = 'e13f0f3faea0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('context_documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entity_type', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('entity_id', sa.String(), nullable=True))
        batch_op.create_index('ix_context_documents_entity_type', ['entity_type'], unique=False)
        batch_op.create_index('ix_context_documents_entity_id', ['entity_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('context_documents', schema=None) as batch_op:
        batch_op.drop_index('ix_context_documents_entity_id')
        batch_op.drop_index('ix_context_documents_entity_type')
        batch_op.drop_column('entity_id')
        batch_op.drop_column('entity_type')

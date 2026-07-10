"""context document provenance links (doc↔entity many-to-many)

Adds the ``context_document_links`` table — a many-to-many reference recording
which context documents were used as context for which character/setting (auto
captured when **Build the whole world** mines a doc into an entity, plus manual
links from the entity editor). Distinct from a document's own single
``entity_type``/``entity_id`` OWNERSHIP scope: a link never changes the doc's
storyline-level membership, and one doc may link to several entities.

Purely additive (a new table), so ``create_all`` + the bootstrap reconciler
already stand it up on the persistent dev DB; this migration keeps Alembic's head
in sync.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-10 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'context_document_links',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('doc_id', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['doc_id'], ['context_documents.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('doc_id', 'entity_type', 'entity_id', name='uq_ctxdoc_link'),
    )
    op.create_index('ix_context_document_links_doc_id', 'context_document_links', ['doc_id'])
    op.create_index(
        'ix_context_document_links_entity_type', 'context_document_links', ['entity_type']
    )
    op.create_index(
        'ix_context_document_links_entity_id', 'context_document_links', ['entity_id']
    )


def downgrade() -> None:
    op.drop_index('ix_context_document_links_entity_id', table_name='context_document_links')
    op.drop_index('ix_context_document_links_entity_type', table_name='context_document_links')
    op.drop_index('ix_context_document_links_doc_id', table_name='context_document_links')
    op.drop_table('context_document_links')

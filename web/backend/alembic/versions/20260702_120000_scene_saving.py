"""scene saving: persist turn traces + session recency

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-02 12:00:00

Adds the ``turn_traces`` table (durable per-turn diagnostic trace — graph/RAG/thinking
steps so a reopened scene is fully reviewable/exportable) and the
``play_sessions.updated_at`` / ``closed_at`` recency columns (resume + save-on-close).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'turn_traces',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column(
            'session_id',
            sa.String(),
            sa.ForeignKey('play_sessions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'scenario_id',
            sa.String(),
            sa.ForeignKey('scenarios.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('turn', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('n', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('step', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False, server_default=''),
        sa.Column('detail', sa.String(), nullable=False, server_default=''),
        sa.Column(
            'data',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_turn_traces_session_id', 'turn_traces', ['session_id'])
    op.create_index('ix_turn_traces_scenario_id', 'turn_traces', ['scenario_id'])

    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True)
        )
    # Backfill existing sessions so ``updated_at`` is never null, then enforce NOT NULL.
    op.execute(
        sa.text('UPDATE play_sessions SET updated_at = created_at WHERE updated_at IS NULL')
    )
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.alter_column(
            'updated_at', existing_type=sa.DateTime(timezone=True), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.drop_column('closed_at')
        batch_op.drop_column('updated_at')
    op.drop_index('ix_turn_traces_scenario_id', table_name='turn_traces')
    op.drop_index('ix_turn_traces_session_id', table_name='turn_traces')
    op.drop_table('turn_traces')

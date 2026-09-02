"""character memories

Adds the ``character_memories`` table: per-character episodic memory of specific
moments, each with a verbatim quote and the subjects it is about. New table, no
existing column touched — coexists with the create_all reconciler.

Revision ID: cm01a4d7f2b9
Revises: d2e3f4a5b6c7
Create Date: 2026-09-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cm01a4d7f2b9'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'character_memories',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('storyline_id', sa.String(), nullable=False),
        sa.Column('character_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('scenario_id', sa.String(), nullable=False),
        sa.Column('turn_seq', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('event_id', sa.String(), nullable=True),
        sa.Column('gloss', sa.String(), nullable=False, server_default=''),
        sa.Column('quote', sa.String(), nullable=True),
        sa.Column('quote_speaker_id', sa.String(), nullable=True),
        sa.Column('valence', sa.String(), nullable=False, server_default=''),
        sa.Column('salience', sa.Float(), nullable=False, server_default='0'),
        sa.Column('participants', sa.JSON(), nullable=True),
        sa.Column('subjects', sa.JSON(), nullable=True),
        sa.Column('reinforcements', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_recalled_seq', sa.Integer(), nullable=True),
        sa.Column('last_recalled_session_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['storyline_id'], ['storylines.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['play_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_character_memories_storyline_id', 'character_memories', ['storyline_id'])
    op.create_index('ix_character_memories_character_id', 'character_memories', ['character_id'])
    op.create_index('ix_character_memories_session_id', 'character_memories', ['session_id'])
    op.create_index('ix_character_memories_scenario_id', 'character_memories', ['scenario_id'])
    # Recall's one query per turn.
    op.create_index('ix_character_memories_owner', 'character_memories', ['storyline_id', 'character_id'])
    # Rewind's delete, and the lineage cut at a fork point.
    op.create_index('ix_character_memories_origin', 'character_memories', ['session_id', 'turn_seq'])


def downgrade() -> None:
    op.drop_index('ix_character_memories_origin', table_name='character_memories')
    op.drop_index('ix_character_memories_owner', table_name='character_memories')
    op.drop_index('ix_character_memories_scenario_id', table_name='character_memories')
    op.drop_index('ix_character_memories_session_id', table_name='character_memories')
    op.drop_index('ix_character_memories_character_id', table_name='character_memories')
    op.drop_index('ix_character_memories_storyline_id', table_name='character_memories')
    op.drop_table('character_memories')

"""session-scoped stat values + a per-stat carry_over flag

Owner decision D-1 (2026-08-21). Stat values were global to a character, so two
play-throughs of one scenario shared a health value and a rewind could only reconcile to
whichever session happened to be open.

``session_character_stats`` holds the value **inside one play-through**; ``character_stats``
keeps the authored baseline. ``stat_definitions.carry_over`` decides whether a play-through
inherits that baseline (``NULL``/false → it starts from the definition's ``default``).

Nothing is backfilled: an existing play-through simply has no session rows yet, so every
stat reads through to the baseline or the default exactly as before, and the first change
inside that play-through writes a session row.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-22 10:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('stat_definitions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('carry_over', sa.Boolean(), nullable=True))

    op.create_table(
        'session_character_stats',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('character_id', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['play_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'session_id', 'character_id', 'key', name='uq_session_stat_session_char_key'
        ),
    )
    op.create_index(
        'ix_session_character_stats_session_id', 'session_character_stats', ['session_id']
    )
    op.create_index(
        'ix_session_character_stats_character_id', 'session_character_stats', ['character_id']
    )


def downgrade() -> None:
    op.drop_index('ix_session_character_stats_character_id', table_name='session_character_stats')
    op.drop_index('ix_session_character_stats_session_id', table_name='session_character_stats')
    op.drop_table('session_character_stats')
    with op.batch_alter_table('stat_definitions', schema=None) as batch_op:
        batch_op.drop_column('carry_over')

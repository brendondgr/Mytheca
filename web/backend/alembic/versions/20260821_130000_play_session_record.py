"""play-through record: name + fork lineage on play_sessions

A scenario may now hold many play-throughs, listed and switched in the story player's
play-through tray. ``name`` is the player's own label (``NULL`` falls back to the
play-through's first non-empty player line). ``parent_session_id`` + ``fork_seq`` are set
together on a session forked from another — a branch, or the pre-cut snapshot a rewind
keeps — and record which session it came from and the parent ``events.seq`` the copy ran
through, inclusive.

All three are nullable, so existing rows read as an unnamed, unforked play-through and
behave exactly as they did.

``parent_session_id`` is ``ON DELETE SET NULL`` rather than CASCADE on purpose: deleting
the play-through you branched *from* must orphan the branch, not delete it.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-21 13:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('parent_session_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('fork_seq', sa.Integer(), nullable=True))
        batch_op.create_index(
            'ix_play_sessions_parent_session_id', ['parent_session_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_play_sessions_parent_session_id',
            'play_sessions',
            ['parent_session_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_play_sessions_parent_session_id', type_='foreignkey')
        batch_op.drop_index('ix_play_sessions_parent_session_id')
        batch_op.drop_column('fork_seq')
        batch_op.drop_column('parent_session_id')
        batch_op.drop_column('name')

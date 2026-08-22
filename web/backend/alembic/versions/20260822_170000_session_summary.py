"""rolling per-session scene memory (history compaction)

Once a session outgrows the fitted transcript window the oldest beats are dropped — which is
how a scene forgets that someone already confessed, already left, already promised. These
three columns hold the summary that replaces them.

``summary_text`` is the rolling recap (``agents/recap_agent``), ``summary_through_seq`` is the
highest ``events.seq`` it covers, and ``summary_updated_at`` records when it last changed.

``summary_through_seq`` is the load-bearing one: it makes the summary **invalidatable**. A
rewind, a beat edit or a re-roll at or below that seq means the summary describes a scene that
no longer happened, so it is cleared rather than left to lie — a stale summary is worse than
none, because the cast would confidently remember the beats the player just removed.

Stored on the session rather than written as an event: an event would take a ``seq``, appear
in the transcript and the export, and be something a player could rewind *to*, none of which
is true of a summary.

All three nullable, so every existing play-through reads as "nothing summarised yet".

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-22 17:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('summary_text', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('summary_through_seq', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('summary_updated_at', sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.drop_column('summary_updated_at')
        batch_op.drop_column('summary_through_seq')
        batch_op.drop_column('summary_text')

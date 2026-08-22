"""standing direction: what the turn could not deliver, carried forward

A scene direction used to die with the turn it rode in on — anything the beats did not
reach was simply gone. That is most of why a direction "gets forgotten": not that the
engine mis-scheduled it, but that nothing outlived the turn to re-owe it.

``play_sessions.standing_direction`` holds the outstanding requirements as a JSON list of
``{"id", "text", "actorId", "pinned", "fromTurn"}``. The next turn merges them ahead of
whatever is newly asked for (oldest debt first) and writes back whatever is still
undelivered; an empty list is written back as NULL.

Nullable, so every existing play-through reads as "owed nothing" and behaves exactly as it
did. It is stored rather than derived from the ``direction`` trace rows on purpose: making
the turn loop's correctness depend on diagnostics being retained would be a trap, since
traces are the first thing an operator prunes.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-22 14:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('standing_direction', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('play_sessions', schema=None) as batch_op:
        batch_op.drop_column('standing_direction')

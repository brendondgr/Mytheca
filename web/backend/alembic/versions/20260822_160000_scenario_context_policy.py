"""scenario context policy: auto-fit the transcript window, or keep a fixed depth

The per-scene "Number of beats" slider asked the player to pick a context-window depth. That
is a question only the app can answer — the right depth is whatever the model can actually
hold, and the app knows the model's window while the player does not.

``scenarios.context_policy`` is how a scene opts out. ``NULL`` (and ``"auto"``) means the
window fits itself to the model's real context budget each turn; ``"fixed"`` restores the
old behaviour and honours ``context_beats``, which is otherwise ignored.

Nullable, so every existing scenario reads as ``auto`` and immediately benefits. The research
harnesses set it to ``"fixed"`` explicitly, because an experiment needs the depth it asked for
rather than a moving target.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-22 16:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('context_policy', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('context_policy')

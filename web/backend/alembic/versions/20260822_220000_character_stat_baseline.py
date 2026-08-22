"""the authored stat value, kept recoverable

``CharacterStat.value`` is not safe to treat as the authored value: at session close
``session_stats.carry_forward`` overwrites it for any stat marked ``carry_over``, so a
character who has been played once no longer remembers what they were written with, and there
was no way back.

Play itself never writes this table (owner decision D-1 — it writes ``session_character_stats``),
so this column exists for exactly one hazard: the carry-forward write. It is set on an
authoring write, and captured **once** by the first carry-forward that would destroy it — a
second capture would overwrite the baseline with the first carry's result, and "back to how
they were written" would drift a scene at a time until it meant nothing.

NULL means "never carried, so ``value`` is still the authored one", which is why a reset of a
never-played character is a no-op rather than an error.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-08-22 22:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('character_stats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('baseline', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('character_stats', schema=None) as batch_op:
        batch_op.drop_column('baseline')

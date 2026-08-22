"""a character's own voice-looseness bias

``looseness`` is a BIAS on top of the beat's register, in ``[-2, +2]``, NULL meaning neutral.
It nudges the register's ``top_p`` by ``character_turn_agent._LOOSENESS_STEP`` per step and
moves **nothing else** — the frequency and presence penalty columns stay at 0.0, because
EXP-2026-08-007 measured those penalties degrading the sentence structure of character prose.

Nullable with no server default: "neutral" is the overwhelming majority state and writing a
0 into every existing row would claim a decision nobody made.

A migration rather than leaving it to the additive reconciler, because
``utils/tests/backend/data/test_alembic.py::test_baseline_columns_match_create_all`` requires
``alembic upgrade head`` and ``create_all`` to produce the same columns.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-22 20:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('looseness', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_column('looseness')

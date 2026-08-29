"""narrative style guide on the storyline, overridable per scenario

``style_blocks`` is a world's NARRATIVE STYLE GUIDE — ``{block id -> text}`` over the six
blocks in ``content/style_blocks`` (attention · voice · pacing · texture · never ·
signature). It says *how this story is written*, where the World Primer says what is true in
it. Five of the six ride in the cached system prefix and are paid for once per scene; only
``signature`` sits in the volatile recency tail.

The scenario column holds per-scene overrides, composed as an appended DELTA on top of the
world's guide rather than substituted into it — see ``services/style_guide`` for why that
placement is load-bearing for the prompt cache.

Both nullable with no server default, so every world and scene written before this feature
reads as "no style" and behaves exactly as it did. That is the correct answer for an
optional feature: nothing is forced to adopt it.

A migration rather than leaving it to the additive reconciler, because
``utils/tests/backend/data/test_alembic.py::test_baseline_columns_match_create_all`` requires
``alembic upgrade head`` and ``create_all`` to produce the same columns.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-08-29 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b0c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('storylines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('style_blocks', sa.JSON(), nullable=True))
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('style_blocks', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('style_blocks')
    with op.batch_alter_table('storylines', schema=None) as batch_op:
        batch_op.drop_column('style_blocks')

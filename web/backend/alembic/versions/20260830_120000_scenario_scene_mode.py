"""which engine a scene's turns run on

``scene_mode`` is the top-level choice, above ``scene_flow``: ``"structured"`` is everything
that shipped before free-text mode — the intent read, the whole-turn plan, registers, and
prose decomposed into attributed beats — and ``"freetext"`` is one unbroken passage per turn
with nobody scheduled and nothing attributed.

Nullable with no server default, and ``NULL`` reads as ``"structured"``. That is deliberately
the opposite of how ``scene_flow``'s ``NULL`` resolves: a *flow* decides how prose is produced
and both of its answers are a scene of attributed beats, where a *mode* decides what a turn
is. No scene written before this column may be moved onto a different engine by its own
silence.

A migration rather than leaving it to the additive reconciler, because
``utils/tests/backend/data/test_alembic.py::test_baseline_columns_match_create_all`` requires
``alembic upgrade head`` and ``create_all`` to produce the same columns.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-30 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scene_mode', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('scene_mode')

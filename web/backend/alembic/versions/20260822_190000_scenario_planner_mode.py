"""whether the scene runs the ReAct planner or the model-free scripted beat order

``planner_mode`` is the scene's default for the single largest latency lever a player has:
EXP-2026-08-005 measured ``planner_agent`` at 41 % of all turn time. ``"off"`` runs the turn
on ``services/beat_order`` — no model call for beat selection, and no register, stakes,
narrator interstitials or exits, which is a real loss and is stated at the control.

Nullable with no server default: NULL reads as ``"planner"``, so every existing scene keeps
the behaviour that shipped.

A migration rather than leaving it to the additive reconciler, because
``utils/tests/backend/data/test_alembic.py::test_baseline_columns_match_create_all`` requires
``alembic upgrade head`` and ``create_all`` to produce the same columns.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-22 19:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('planner_mode', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('planner_mode')

"""the named scene preset the play controls were last set from

A preset (``content/scene_presets``) is a named point in the space ``max_turns`` /
``suggestions_count`` / ``beat_length`` already describe. This column records **which one the
player chose**, not what the scene is: the controls stay authoritative, so moving one leaves
this set and the UI can say "modified" and offer a reset to it.

Nullable with **no server default**, because "no preset" (Custom) is a real and common state
rather than a value waiting to be filled in. Every existing scenario reads as Custom.

The additive reconciler would self-heal this column at preflight, but
``utils/tests/backend/data/test_alembic.py::test_baseline_columns_match_create_all`` requires
that ``alembic upgrade head`` and ``create_all`` agree — so a migration is not optional here
regardless of how the column would otherwise arrive.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-22 18:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scene_preset', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('scene_preset')

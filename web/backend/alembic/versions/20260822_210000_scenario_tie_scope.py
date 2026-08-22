"""how much of a speaker's relationship history reaches their beat

``tie_scope`` is the scene's default for the story graph's prompt-side reach:

* ``"addressed"`` — only the addressee's ties, which is what shipped before the control.
* ``"scene"`` — everyone present. NULL reads as this, and it is the default: a speaker
  carrying only the addressee's history is why two characters could stand in the same room
  with a decade between them and neither mention it. Costs no new query.
* ``"world"`` — plus the speaker's off-scene ties (``graph_reader.offscene_ties``), the only
  query the feature adds. Non-default deliberately: at this stop a character may mention
  somebody the scene has never introduced, which is a product question, not a bug.

Nullable with no server default, so every existing scene reads as ``"scene"``.

A migration rather than leaving it to the additive reconciler, because
``utils/tests/backend/data/test_alembic.py::test_baseline_columns_match_create_all`` requires
``alembic upgrade head`` and ``create_all`` to produce the same columns.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-08-22 21:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tie_scope', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('tie_scope')

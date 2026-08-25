"""how a scene's prose is produced — one call per speaker, or one for the whole turn

``scene_flow`` is the scene's default for ``agents/scene_script_agent``:

* ``"voiced"`` — one model call per speaker, each carrying that character's voice samples,
  register and relationship note. What has always shipped, and what keeps voices apart.
  **NULL reads as this**, so every scene written before this column keeps exactly the
  behaviour it had.
* ``"continuous"`` — ONE call writes the whole planned turn, marking each change of speaker
  with ``<speaker:N>``. Flows better and attributes from a token the writer emitted rather
  than from the engine guessing; the cost is that every voice sample shares one prompt, and
  that cost falls hardest on the weaker models this is meant to be robust on.

Which of the two reads better is **unmeasured** — see ``docs/checklist.md`` for the
experiment that would settle it. That is why this is a per-scene column with a conservative
default rather than a change of behaviour.

A migration rather than leaving it to the additive reconciler, because
``utils/tests/backend/data/test_alembic.py::test_baseline_columns_match_create_all`` requires
``alembic upgrade head`` and ``create_all`` to produce the same columns.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-08-24 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b0c1d2e3f4a5'
down_revision: Union[str, None] = 'a9b0c1d2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scene_flow', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scenarios', schema=None) as batch_op:
        batch_op.drop_column('scene_flow')

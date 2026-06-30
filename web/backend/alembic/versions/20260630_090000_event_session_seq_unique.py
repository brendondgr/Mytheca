"""event (session_id, seq) unique constraint

Revision ID: f1a2b3c4d5e6
Revises: e7a8b9c0d1f2
Create Date: 2026-06-30 09:00:00

Makes ``seq`` monotonic per session a hard invariant for the turn engine
(``max(seq)+1``) and catches concurrent-write races. Additive-only; the reconciler
self-heals columns but not constraints, so this ships as a migration for Postgres
(SQLite tests build it from the model via ``create_all``).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e7a8b9c0d1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_event_session_seq', ['session_id', 'seq'])


def downgrade() -> None:
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_constraint('uq_event_session_seq', type_='unique')

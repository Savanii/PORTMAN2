"""jnpa phase1 - lueu_parcel_log gains is_shortclose

Short-close flag: a log row that carries the leftover (unfilled) parcel quantity
with no time, entered via the LUEU01 "Shortclose Remaining" button. Counts toward
completion (Remaining -> 0) but is excluded from the average flow rate.

Revision ID: jnpa36_lueu_shortclose
Revises: jnpa35_export_parcel_mirror
Create Date: 2026-07-01
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa36_lueu_shortclose'
down_revision: Union[str, None] = 'jnpa35_export_parcel_mirror'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE lueu_parcel_log ADD COLUMN IF NOT EXISTS is_shortclose BOOLEAN DEFAULT FALSE;')


def downgrade() -> None:
    op.execute('ALTER TABLE lueu_parcel_log DROP COLUMN IF EXISTS is_shortclose;')

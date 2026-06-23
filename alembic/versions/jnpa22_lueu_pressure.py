"""jnpa phase1 - LUEU parcel log gains pressure

Revision ID: jnpa22_lueu_pressure
Revises: jnpa21_drop_ldud_survey_ops
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa22_lueu_pressure'
down_revision: Union[str, None] = 'jnpa21_drop_ldud_survey_ops'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE lueu_parcel_log ADD COLUMN IF NOT EXISTS pressure NUMERIC;')


def downgrade() -> None:
    op.execute('ALTER TABLE lueu_parcel_log DROP COLUMN IF EXISTS pressure;')

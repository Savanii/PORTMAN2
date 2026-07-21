"""Add PDM01 Type 2 classification.

Revision ID: jnpa49_pdm01_type_2
Revises: jnpa48_ldud_soft_delete
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'jnpa49_pdm01_type_2'
down_revision: Union[str, None] = 'jnpa48_ldud_soft_delete'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE port_delay_types ADD COLUMN IF NOT EXISTS type_2 TEXT')


def downgrade() -> None:
    op.execute('ALTER TABLE port_delay_types DROP COLUMN IF EXISTS type_2')

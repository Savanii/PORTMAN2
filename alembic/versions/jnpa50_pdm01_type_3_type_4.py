"""Add PDM01 Type 3 and Type 4 classifications.

Revision ID: jnpa50_pdm01_type_3_type_4
Revises: jnpa49_pdm01_type_2
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'jnpa50_pdm01_type_3_type_4'
down_revision: Union[str, None] = 'jnpa49_pdm01_type_2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE port_delay_types
            ADD COLUMN IF NOT EXISTS type_3 TEXT,
            ADD COLUMN IF NOT EXISTS type_4 TEXT;
    ''')


def downgrade() -> None:
    op.execute('''
        ALTER TABLE port_delay_types
            DROP COLUMN IF EXISTS type_3,
            DROP COLUMN IF EXISTS type_4;
    ''')

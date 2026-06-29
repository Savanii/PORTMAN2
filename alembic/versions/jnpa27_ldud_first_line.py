"""jnpa phase1 - LDUD header gains first_line (First Line Ashore)

Revision ID: jnpa27_ldud_first_line
Revises: jnpa26_port_master_code
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa27_ldud_first_line'
down_revision: Union[str, None] = 'jnpa26_port_master_code'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS first_line TEXT;')


def downgrade() -> None:
    op.execute('ALTER TABLE ldud_header DROP COLUMN IF EXISTS first_line;')

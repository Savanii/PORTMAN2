"""jnpa phase1 - VCN header gains pbl (Parallel Body Length)

Entered on the VCN header; on save it is written back to the VC01 vessel
master (vessels.pbl) for that vessel.

Revision ID: jnpa23_vcn_pbl
Revises: jnpa22_lueu_pressure
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa23_vcn_pbl'
down_revision: Union[str, None] = 'jnpa22_lueu_pressure'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS pbl NUMERIC(10,2);')


def downgrade() -> None:
    op.execute('ALTER TABLE vcn_header DROP COLUMN IF EXISTS pbl;')

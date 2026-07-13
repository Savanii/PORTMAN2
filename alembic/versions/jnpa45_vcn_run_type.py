"""jnpa phase1 - VCN header: drop type_of_discharge, add vessel_run_type

The old free-text Full/Partial Discharge/Load field is replaced by a
vessel_run_type sourced from the VRT01 Vessel Run Type Master.

Revision ID: jnpa45_vcn_run_type
Revises: jnpa44_mis_history_vcg01_align
Create Date: 2026-07-13
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa45_vcn_run_type'
down_revision: Union[str, None] = 'jnpa44_mis_history_vcg01_align'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS vessel_run_type TEXT;')
    op.execute('ALTER TABLE vcn_header DROP COLUMN IF EXISTS type_of_discharge;')


def downgrade() -> None:
    op.execute('ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS type_of_discharge TEXT;')
    op.execute('ALTER TABLE vcn_header DROP COLUMN IF EXISTS vessel_run_type;')

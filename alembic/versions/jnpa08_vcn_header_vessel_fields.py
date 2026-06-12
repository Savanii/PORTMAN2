"""jnpa phase1 - add LOA/draft/NOR/berth to vcn_header for EV01 Move to VCN

Revision ID: jnpa08_vcn_vessel_fields
Revises: jnpa07_ev01_qty_text
Create Date: 2026-06-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa08_vcn_vessel_fields'
down_revision: Union[str, None] = 'jnpa07_ev01_qty_text'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS loa NUMERIC(10,2);
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS draft NUMERIC(10,2);
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS nor_tendered TIMESTAMPTZ;
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS berth_name TEXT;
    ''')


def downgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS loa;
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS draft;
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS nor_tendered;
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS berth_name;
    ''')

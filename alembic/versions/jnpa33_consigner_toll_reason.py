"""jnpa phase1 - vcn_consigners gains toll_reason

When a parcel's Toll Applicable flag is turned off in VCN01, the operator must
record why — stored here.

Revision ID: jnpa33_consigner_toll_reason
Revises: jnpa32_port_default_discharge
Create Date: 2026-06-30
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa33_consigner_toll_reason'
down_revision: Union[str, None] = 'jnpa32_port_default_discharge'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS toll_reason TEXT;')


def downgrade() -> None:
    op.execute('ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS toll_reason;')

"""jnpa phase1 - port_master gains is_default_discharge

One port can be flagged as the default discharge port (VPM01 radio). VCN01
auto-fills the Discharge Port on new vessel calls from it. A partial unique
index enforces at most one default.

Revision ID: jnpa32_port_default_discharge
Revises: jnpa31_consigner_toll_equipment
Create Date: 2026-06-30
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa32_port_default_discharge'
down_revision: Union[str, None] = 'jnpa31_consigner_toll_equipment'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE port_master ADD COLUMN IF NOT EXISTS is_default_discharge BOOLEAN DEFAULT FALSE;')
    op.execute('''CREATE UNIQUE INDEX IF NOT EXISTS ux_port_master_one_default
                  ON port_master (is_default_discharge) WHERE is_default_discharge;''')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ux_port_master_one_default;')
    op.execute('ALTER TABLE port_master DROP COLUMN IF EXISTS is_default_discharge;')

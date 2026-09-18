"""VCN01 berthing delays sub-table (Along Side -> Cast Off window)

Same shape as vcn_delays, but bounded by LDUD01's Along Side / Cast Off times
instead of Anchorage / Pilot Pickup, and classified by two fixed axes:
port_type (Port | Non Port) and service_type (Marine | Operations).

Kept as its own table rather than a flag on vcn_delays: RP01's delay reports
read vcn_delays directly and would silently start counting these.

Revision ID: jnpa69_vcn_berth_delays
Revises: jnpa68_retire_shore_gangway
Create Date: 2026-09-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa69_vcn_berth_delays'
down_revision: Union[str, None] = 'jnpa68_retire_shore_gangway'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS vcn_berth_delays (
            id SERIAL PRIMARY KEY,
            vcn_id INTEGER NOT NULL,
            port_type TEXT,
            service_type TEXT,
            delay_start TEXT,
            delay_end TEXT,
            FOREIGN KEY (vcn_id) REFERENCES vcn_header(id) ON DELETE CASCADE
        );
    ''')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS vcn_berth_delays;')

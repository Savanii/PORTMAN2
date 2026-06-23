"""jnpa phase1 - per-cargo quota on a VCN

Captured on the EV01->VCN move from the IGM/daily-report cargo totals.
VCN01 shows available-per-cargo and blocks parcels that exceed it.
Separate from vcn_cargo_declaration (which LDUD reads) to avoid double-counting.

Revision ID: jnpa25_vcn_cargo_quota
Revises: jnpa24_ldud_vcn_unique
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa25_vcn_cargo_quota'
down_revision: Union[str, None] = 'jnpa24_ldud_vcn_unique'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS vcn_cargo_quota (
            id SERIAL PRIMARY KEY,
            vcn_id INTEGER NOT NULL,
            cargo_name TEXT NOT NULL,
            total_qty NUMERIC,
            UNIQUE (vcn_id, cargo_name),
            FOREIGN KEY (vcn_id) REFERENCES vcn_header(id) ON DELETE CASCADE
        );
    ''')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS vcn_cargo_quota;')

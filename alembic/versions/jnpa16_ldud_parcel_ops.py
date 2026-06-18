"""jnpa phase1 - LDUD parcel operations + departure header fields

Adds:
  - ldud_header departure/ops timing columns
  - ldud_parcel_ops sub-table: one row per parcel (or per MERGED group of
    same-cargo parcels), capturing start/end datetime.
    parcel_ids = CSV of vcn_consigners.id (1 normally, 2+ when merged).

Revision ID: jnpa16_ldud_parcel_ops
Revises: jnpa15_vcn_parcel_identity
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa16_ldud_parcel_ops'
down_revision: Union[str, None] = 'jnpa15_vcn_parcel_identity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS alongside_datetime TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS ops_commenced TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS cast_off_datetime TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS pilot_board_departure TEXT;
        ALTER TABLE ldud_header ADD COLUMN IF NOT EXISTS pilot_disembarked TEXT;

        CREATE TABLE IF NOT EXISTS ldud_parcel_ops (
            id SERIAL PRIMARY KEY,
            ldud_id INTEGER NOT NULL,
            parcel_ids TEXT,
            cargo_name TEXT,
            start_dt TEXT,
            end_dt TEXT,
            FOREIGN KEY (ldud_id) REFERENCES ldud_header(id) ON DELETE CASCADE
        );
    ''')


def downgrade() -> None:
    op.execute('''
        DROP TABLE IF EXISTS ldud_parcel_ops;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS pilot_disembarked;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS pilot_board_departure;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS cast_off_datetime;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS ops_commenced;
        ALTER TABLE ldud_header DROP COLUMN IF EXISTS alongside_datetime;
    ''')

"""jnpa phase1 - IGM fields move to vcn_header; drop vcn_nominations

Cargo is now declared in the VCN consigner (customer details) table, so the
import Cargo Declaration UI is removed from VCN01 and its IGM Manual No /
IGM Date move to the header (backfilled from existing declarations).

NOTE: vcn_cargo_declaration itself is intentionally NOT dropped — billing
(FIN01/FINV01/FDCN01), LDUD01 and LUEU01 still read it for historic data.

Revision ID: jnpa11_igm_header_drop_noms
Revises: jnpa10_consigner_quantity
Create Date: 2026-06-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa11_igm_header_drop_noms'
down_revision: Union[str, None] = 'jnpa10_consigner_quantity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS igm_manual_number TEXT;
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS igm_date TEXT;

        UPDATE vcn_header h
        SET igm_manual_number = COALESCE(h.igm_manual_number, cd.igm_manual_number),
            igm_date          = COALESCE(h.igm_date, cd.igm_date)
        FROM (
            SELECT DISTINCT ON (vcn_id) vcn_id, igm_manual_number, igm_date
            FROM vcn_cargo_declaration
            WHERE igm_manual_number IS NOT NULL OR igm_date IS NOT NULL
            ORDER BY vcn_id, id
        ) cd
        WHERE cd.vcn_id = h.id;

        DROP TABLE IF EXISTS vcn_nominations;
    ''')


def downgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS vcn_nominations (
            id SERIAL PRIMARY KEY,
            vcn_id INTEGER NOT NULL,
            eta TEXT,
            etd TEXT,
            vessel_run_type TEXT,
            arrival_fore_draft REAL,
            arrival_after_draft REAL,
            FOREIGN KEY (vcn_id) REFERENCES vcn_header(id) ON DELETE CASCADE
        );
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS igm_manual_number;
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS igm_date;
    ''')

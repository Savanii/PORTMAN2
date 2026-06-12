"""jnpa phase1 - consigner rows become IGM lines; IGM PDF stored on header

Each vcn_consigners row now maps to one FORM III (IGM) line: line no, BL no,
BL date, one cargo + quantity, consignee and importer (both from customer
master). The IGM PDF itself is stored on vcn_header as BYTEA. The header-level
IGM Manual No / IGM Date (added in jnpa11) are superseded by the per-line
fields and dropped again.

Revision ID: jnpa12_consigner_igm_lines
Revises: jnpa11_igm_header_drop_noms
Create Date: 2026-06-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa12_consigner_igm_lines'
down_revision: Union[str, None] = 'jnpa11_igm_header_drop_noms'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS igm_line_no TEXT;
        ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS bl_no TEXT;
        ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS bl_date TEXT;
        ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS importer_name TEXT;

        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS igm_document BYTEA;
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS igm_document_name TEXT;

        ALTER TABLE vcn_header DROP COLUMN IF EXISTS igm_manual_number;
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS igm_date;
    ''')


def downgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS igm_line_no;
        ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS bl_no;
        ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS bl_date;
        ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS importer_name;

        ALTER TABLE vcn_header DROP COLUMN IF EXISTS igm_document;
        ALTER TABLE vcn_header DROP COLUMN IF EXISTS igm_document_name;

        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS igm_manual_number TEXT;
        ALTER TABLE vcn_header ADD COLUMN IF NOT EXISTS igm_date TEXT;
    ''')

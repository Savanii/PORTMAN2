"""jnpa phase1 - parcel identity on vcn_export_cargo_declaration

Extends the parcel system to Export VCNs: each export cargo declaration row
becomes a first-class parcel, mirroring vcn_consigners (jnpa15).
  - parcel_seq : ordinal within the vessel call (1,2,3...)
  - parcel_no  : stored label '<vcn_doc_num>/P<seq>'

Revision ID: jnpa18_export_parcel_identity
Revises: jnpa17_drop_ldud_op_tables
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa18_export_parcel_identity'
down_revision: Union[str, None] = 'jnpa17_drop_ldud_op_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_export_cargo_declaration ADD COLUMN IF NOT EXISTS parcel_seq INTEGER;
        ALTER TABLE vcn_export_cargo_declaration ADD COLUMN IF NOT EXISTS parcel_no TEXT;

        WITH ordered AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY vcn_id ORDER BY id) AS seq
            FROM vcn_export_cargo_declaration
        )
        UPDATE vcn_export_cargo_declaration c
        SET parcel_seq = o.seq
        FROM ordered o
        WHERE o.id = c.id;

        UPDATE vcn_export_cargo_declaration c
        SET parcel_no = h.vcn_doc_num || '/P' || c.parcel_seq
        FROM vcn_header h
        WHERE h.id = c.vcn_id AND c.parcel_seq IS NOT NULL;
    ''')


def downgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_export_cargo_declaration DROP COLUMN IF EXISTS parcel_no;
        ALTER TABLE vcn_export_cargo_declaration DROP COLUMN IF EXISTS parcel_seq;
    ''')

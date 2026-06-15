"""jnpa phase1 - parcel identity on vcn_consigners; parcel_id on ldud ops

Each vcn_consigners row becomes a first-class parcel:
  - parcel_seq : ordinal within the vessel call (1,2,3...)
  - parcel_no  : stored label '<vcn_doc_num>/P<seq>' e.g. 'VCN-2627-002/P1'
ldud_vessel_operations gains a nullable parcel_id (FK -> vcn_consigners.id).

Revision ID: jnpa15_vcn_parcel_identity
Revises: jnpa14_vcn_via_remarks
Create Date: 2026-06-15
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa15_vcn_parcel_identity'
down_revision: Union[str, None] = 'jnpa14_vcn_via_remarks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS parcel_seq INTEGER;
        ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS parcel_no TEXT;

        WITH ordered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY vcn_id
                       ORDER BY (substring(igm_line_no from '^[0-9]+'))::int NULLS LAST, id
                   ) AS seq
            FROM vcn_consigners
        )
        UPDATE vcn_consigners c
        SET parcel_seq = o.seq
        FROM ordered o
        WHERE o.id = c.id;

        UPDATE vcn_consigners c
        SET parcel_no = h.vcn_doc_num || '/P' || c.parcel_seq
        FROM vcn_header h
        WHERE h.id = c.vcn_id AND c.parcel_seq IS NOT NULL;

        ALTER TABLE ldud_vessel_operations ADD COLUMN IF NOT EXISTS parcel_id INTEGER;
    ''')


def downgrade() -> None:
    op.execute('''
        ALTER TABLE ldud_vessel_operations DROP COLUMN IF EXISTS parcel_id;
        ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS parcel_no;
        ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS parcel_seq;
    ''')

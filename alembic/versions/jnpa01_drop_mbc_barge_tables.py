"""jnpa phase1 - drop mbc and barge tables

Revision ID: jnpa01_drop_mbc_barge
Revises: c0d1e2f3a4b5
Create Date: 2026-04-28
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa01_drop_mbc_barge'
down_revision: Union[str, None] = 'c0d1e2f3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop child tables first (FK order)
    op.execute('DROP TABLE IF EXISTS mbc_proof_documents CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_cleaning_details CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_customer_details CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_export_load_port_lines CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_discharge_port_lines CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_load_port_lines CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_delays CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_header CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_master CASCADE')
    op.execute('DROP TABLE IF EXISTS mbc_doc_series CASCADE')
    # VEX tables
    op.execute('DROP TABLE IF EXISTS vex_mbc_lines CASCADE')
    op.execute('DROP TABLE IF EXISTS vex_barge_lines CASCADE')
    op.execute('DROP TABLE IF EXISTS vex_header CASCADE')
    # Barge LDUD sub-tables
    op.execute('DROP TABLE IF EXISTS ldud_barge_cleaning CASCADE')
    op.execute('DROP TABLE IF EXISTS ldud_barge_lines CASCADE')
    # Barge master
    op.execute('DROP TABLE IF EXISTS barges CASCADE')
    # Payloader master (only used for barge cleaning)
    op.execute('DROP TABLE IF EXISTS port_payloaders CASCADE')
    # Remove barge_name column from lueu_lines if it exists
    op.execute('ALTER TABLE lueu_lines DROP COLUMN IF EXISTS barge_name')


def downgrade() -> None:
    pass  # intentional: JNPA does not restore barge/MBC tables

"""jnpa phase1 - enforce one LDUD per VCN

Partial unique index on ldud_header.vcn_id (non-null only, so draft LDUDs
without a VCN are unaffected). Backs the application-level check.

Revision ID: jnpa24_ldud_vcn_unique
Revises: jnpa23_vcn_pbl
Create Date: 2026-06-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa24_ldud_vcn_unique'
down_revision: Union[str, None] = 'jnpa23_vcn_pbl'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS ux_ldud_header_vcn_id
        ON ldud_header (vcn_id) WHERE vcn_id IS NOT NULL;
    ''')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ux_ldud_header_vcn_id;')

"""jnpa phase1 - add quantity to vcn_consigners (comma list aligned with cargo_name)

Revision ID: jnpa10_consigner_quantity
Revises: jnpa09_consigners_drop_vsdm
Create Date: 2026-06-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa10_consigner_quantity'
down_revision: Union[str, None] = 'jnpa09_consigners_drop_vsdm'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE vcn_consigners ADD COLUMN IF NOT EXISTS quantity TEXT')


def downgrade() -> None:
    op.execute('ALTER TABLE vcn_consigners DROP COLUMN IF EXISTS quantity')

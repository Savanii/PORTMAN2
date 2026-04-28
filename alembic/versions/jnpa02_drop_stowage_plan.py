"""jnpa phase1 - drop stowage plan table

Revision ID: jnpa02_drop_stowage
Revises: jnpa01_drop_mbc_barge
Create Date: 2026-04-28
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa02_drop_stowage'
down_revision: Union[str, None] = 'jnpa01_drop_mbc_barge'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('DROP TABLE IF EXISTS vcn_stowage_plan CASCADE')


def downgrade() -> None:
    pass

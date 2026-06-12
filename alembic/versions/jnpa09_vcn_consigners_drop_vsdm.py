"""jnpa phase1 - add vcn_consigners sub-table; remove VSDM01 stevedore master

Revision ID: jnpa09_consigners_drop_vsdm
Revises: jnpa08_vcn_vessel_fields
Create Date: 2026-06-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa09_consigners_drop_vsdm'
down_revision: Union[str, None] = 'jnpa08_vcn_vessel_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS vcn_consigners (
            id SERIAL PRIMARY KEY,
            vcn_id INTEGER NOT NULL,
            agent_name TEXT,
            pipeline_name TEXT,
            consigner_name TEXT,
            unload_terminal TEXT,
            cargo_name TEXT,
            FOREIGN KEY (vcn_id) REFERENCES vcn_header(id) ON DELETE CASCADE
        );

        DROP TABLE IF EXISTS contractors CASCADE;
        DELETE FROM module_permissions WHERE module_code = 'VSDM01';
        DELETE FROM module_config WHERE module_code = 'VSDM01';
    ''')


def downgrade() -> None:
    op.execute('''
        DROP TABLE IF EXISTS vcn_consigners;
        CREATE TABLE IF NOT EXISTS contractors (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE
        );
    ''')

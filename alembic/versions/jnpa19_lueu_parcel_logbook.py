"""jnpa phase1 - LUEU01 parcel logbook; drop lueu_lines + route/system masters

Revision ID: jnpa19_lueu_parcel_logbook
Revises: jnpa18_export_parcel_identity
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa19_lueu_parcel_logbook'
down_revision: Union[str, None] = 'jnpa18_export_parcel_identity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS lueu_parcel_log (
            id SERIAL PRIMARY KEY,
            parcel_op_id INTEGER NOT NULL,
            entry_date TEXT,
            from_time TEXT,
            to_time TEXT,
            quantity NUMERIC,
            quantity_uom TEXT,
            medium TEXT,
            equipment_name TEXT,
            delay_name TEXT,
            shift TEXT,
            operator_name TEXT,
            shift_incharge TEXT,
            berth_name TEXT,
            remarks TEXT,
            created_by TEXT,
            created_date TEXT,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_by TEXT,
            deleted_date TEXT,
            FOREIGN KEY (parcel_op_id) REFERENCES ldud_parcel_ops(id) ON DELETE CASCADE
        );
        DROP TABLE IF EXISTS lueu_lines;
        DROP TABLE IF EXISTS conveyor_routes;
        DROP TABLE IF EXISTS port_systems;
    ''')


def downgrade() -> None:
    # Best-effort recreate (no data restored).
    op.execute('''
        DROP TABLE IF EXISTS lueu_parcel_log;
        CREATE TABLE IF NOT EXISTS conveyor_routes (
            id SERIAL PRIMARY KEY, route_name TEXT, is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS port_systems (
            id SERIAL PRIMARY KEY, name TEXT
        );
        CREATE TABLE IF NOT EXISTS lueu_lines (id SERIAL PRIMARY KEY);
    ''')

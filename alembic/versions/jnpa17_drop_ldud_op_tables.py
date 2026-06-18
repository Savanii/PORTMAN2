"""jnpa phase1 - drop legacy LDUD operational sub-tables

Removes the operational capture that the new parcel-centric LDUD flow
(Parcel Operations + header timing fields) replaces:
  ldud_delays, ldud_anchorage, ldud_vessel_operations,
  ldud_hold_completion, ldud_hold_cargo

NOTE: RP01 (Statement of Facts, Vessel Discharged) and FINV01 invoices
still reference these — they will be rebuilt separately and will error
until then. This is intentional per the migration decision.

Revision ID: jnpa17_drop_ldud_op_tables
Revises: jnpa16_ldud_parcel_ops
Create Date: 2026-06-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa17_drop_ldud_op_tables'
down_revision: Union[str, None] = 'jnpa16_ldud_parcel_ops'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        DROP TABLE IF EXISTS ldud_hold_cargo;
        DROP TABLE IF EXISTS ldud_hold_completion;
        DROP TABLE IF EXISTS ldud_vessel_operations;
        DROP TABLE IF EXISTS ldud_anchorage;
        DROP TABLE IF EXISTS ldud_delays;
    ''')


def downgrade() -> None:
    # Best-effort recreate with the full known column set (data is not restored).
    op.execute('''
        CREATE TABLE IF NOT EXISTS ldud_delays (
            id SERIAL PRIMARY KEY,
            ldud_id INTEGER NOT NULL,
            delay_name TEXT,
            delay_account_type TEXT,
            equipment_name TEXT,
            start_datetime TEXT,
            end_datetime TEXT,
            total_time_mins REAL,
            total_time_hrs REAL,
            delays_to_sof TEXT,
            invoiceable TEXT,
            minus_delay_hours TEXT,
            crane_number TEXT,
            FOREIGN KEY (ldud_id) REFERENCES ldud_header(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ldud_anchorage (
            id SERIAL PRIMARY KEY,
            ldud_id INTEGER NOT NULL,
            anchorage_name TEXT,
            anchored TEXT,
            discharge_started TEXT,
            discharge_commenced TEXT,
            anchor_aweigh TEXT,
            cargo_quantity REAL,
            cargo_name TEXT,
            FOREIGN KEY (ldud_id) REFERENCES ldud_header(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ldud_vessel_operations (
            id SERIAL PRIMARY KEY,
            ldud_id INTEGER NOT NULL,
            hold_name TEXT,
            start_time TEXT,
            end_time TEXT,
            cargo_name TEXT,
            quantity NUMERIC,
            parcel_id INTEGER,
            FOREIGN KEY (ldud_id) REFERENCES ldud_header(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ldud_hold_completion (
            id SERIAL PRIMARY KEY,
            ldud_id INTEGER NOT NULL,
            hold_name TEXT,
            commenced TEXT,
            completed TEXT,
            FOREIGN KEY (ldud_id) REFERENCES ldud_header(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ldud_hold_cargo (
            id SERIAL PRIMARY KEY,
            ldud_id INTEGER NOT NULL,
            hold_name TEXT,
            cargo_name TEXT,
            UNIQUE (ldud_id, hold_name),
            FOREIGN KEY (ldud_id) REFERENCES ldud_header(id) ON DELETE CASCADE
        );
    ''')

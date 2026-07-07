"""jnpa phase1 - mis_vessel_master base table for reports

Legacy vessel-call master sheet: one row per vessel call with berthing
timings and turnaround KPIs. Companion to mis_history (parcel lines);
loaded via the RP01 wizard as a full replace (delete + insert).

Excluded from the sheet on purpose: SN serial, Code/Status (live berth
status), daily-update tracking fields, and Excel concat helper columns.

Revision ID: jnpa43_mis_vessel_master
Revises: jnpa42_mis_history
Create Date: 2026-07-07
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa43_mis_vessel_master'
down_revision: Union[str, None] = 'jnpa42_mis_history'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS mis_vessel_master (
            id                    SERIAL PRIMARY KEY,
            fin_year              TEXT,           -- '2024-25'
            month                 TEXT,           -- 'Nov-24'
            berth_no              TEXT,           -- LB-03
            vcn_no                TEXT,           -- 'Via' in the sheet (Q5928)
            vessel_name           TEXT,
            overseas_coastal      TEXT,
            foreign_indian        TEXT,           -- F/I
            imo_no                TEXT,
            flag                  TEXT,
            bhc                   TEXT,
            port_code             TEXT,
            port_of_loading       TEXT,
            grt                   NUMERIC(12,2),
            draft                 NUMERIC(6,2),
            loa                   NUMERIC(8,2),
            import_export         TEXT,
            agent                 TEXT,
            unload_pipeline       TEXT,
            consigner             TEXT,
            unloading_terminal    TEXT,
            new_cat               TEXT,
            category1             TEXT,
            category              TEXT,
            cargo                 TEXT,
            nor                   TEXT,           -- timings: ISO 'YYYY-MM-DDTHH:MM'
            anchorage_time        TEXT,
            pilot_pickup          TEXT,
            first_line            TEXT,
            alongside             TEXT,
            ops_commenced         TEXT,
            cargo_completion      TEXT,
            sail_cast_off         TEXT,
            cast_off              TEXT,
            pilot_board_departure TEXT,
            pilot_disembarked     TEXT,
            quantity              NUMERIC(14,3),
            flow_rate             NUMERIC(10,2),  -- MT/hr
            remarks               TEXT,
            pre_berthing_waiting  NUMERIC(8,2),   -- KPI block (days); port/non-port
            waiting_port          NUMERIC(8,2),   -- split is not derivable from timings
            waiting_non_port      NUMERIC(8,2),
            stay_at_berth         NUMERIC(8,2),
            arrive_to_comm        NUMERIC(8,2),
            working_time          NUMERIC(8,2),
            non_working_total     NUMERIC(8,2),
            non_working_port      NUMERIC(8,2),
            non_working_non_port  NUMERIC(8,2),
            inward_movement       NUMERIC(8,2),
            outward_movement      NUMERIC(8,2),
            uploaded_by           TEXT,
            uploaded_at           TIMESTAMP DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_mis_vm_vcn   ON mis_vessel_master (vcn_no);
        CREATE INDEX IF NOT EXISTS idx_mis_vm_month ON mis_vessel_master (month);
        CREATE INDEX IF NOT EXISTS idx_mis_vm_fy    ON mis_vessel_master (fin_year);
    ''')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS mis_vessel_master;')

"""jnpa phase1 - SAP async queue + integration logs

Revision ID: jnpa40_sap_tables
Revises: jnpa39_bill_vessels
Create Date: 2026-07-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa40_sap_tables'
down_revision: Union[str, None] = 'jnpa39_bill_vessels'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        CREATE TABLE IF NOT EXISTS sap_outbound_queue (
            id              SERIAL PRIMARY KEY,
            job_type        TEXT,
            invoice_id      INTEGER,
            reference_type  TEXT,
            reference_id    INTEGER,
            reference_number TEXT,
            payload         TEXT,
            status          TEXT DEFAULT 'pending',
            retry_count     INTEGER DEFAULT 0,
            max_retries     INTEGER DEFAULT 5,
            next_attempt_at TEXT,
            last_error      TEXT,
            sap_document_number TEXT,
            created_by      TEXT,
            created_date    TEXT,
            updated_date    TEXT
        );
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS ix_sap_outq_status ON sap_outbound_queue (status);')
    op.execute('CREATE INDEX IF NOT EXISTS ix_sap_outq_invoice ON sap_outbound_queue (invoice_id);')
    op.execute('''
        CREATE TABLE IF NOT EXISTS integration_logs (
            id                   SERIAL PRIMARY KEY,
            integration_type     TEXT,
            source_type          TEXT,
            source_id            INTEGER,
            source_reference     TEXT,
            request_url          TEXT,
            request_body         TEXT,
            response_status_code INTEGER,
            response_body        TEXT,
            status               TEXT,
            error_message        TEXT,
            duration_ms          INTEGER,
            created_by           TEXT,
            created_date         TEXT
        );
    ''')


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS integration_logs;')
    op.execute('DROP TABLE IF EXISTS sap_outbound_queue;')

"""jnpa phase1 - retype invoice_header SAP callback date columns

The SAP inbound callback (_apply_record in sap_inbound.py) writes
sap_posting_date / gst_ack_date with ::timestamp / ::date casts. Locally these
columns were TEXT, causing a DatatypeMismatch on every success callback. Retype
them to match the SAP integration contract (TIMESTAMP / DATE), preserving any
existing non-empty values via NULLIF casts.

Revision ID: jnpa41_invoice_sap_date_types
Revises: jnpa40_sap_tables
Create Date: 2026-07-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa41_invoice_sap_date_types'
down_revision: Union[str, None] = 'jnpa40_sap_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE invoice_header ALTER COLUMN sap_posting_date TYPE TIMESTAMP USING NULLIF(sap_posting_date, '')::timestamp;")
    op.execute("ALTER TABLE invoice_header ALTER COLUMN gst_ack_date TYPE DATE USING NULLIF(gst_ack_date, '')::date;")


def downgrade() -> None:
    op.execute("ALTER TABLE invoice_header ALTER COLUMN sap_posting_date TYPE TEXT;")
    op.execute("ALTER TABLE invoice_header ALTER COLUMN gst_ack_date TYPE TEXT;")

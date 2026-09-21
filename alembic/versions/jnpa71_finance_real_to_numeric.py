"""finance: convert money/quantity/rate columns from real -> numeric

Ported from the parent app (PORTMAN c2d3e4f5a6b7), which hit this in prod.

The finance amount/quantity/rate columns were declared `real` (PostgreSQL
float4, ~7 significant digits). Near 1.36M a float4 can only land on multiples
of 0.125, so an exact value like 1360962.46 is physically snapped to 1360962.5
on write. The calculation in JS/Python is correct; the column type silently
truncates it.

Measured on this database before the change:
    142580.87::real  -> 142580.88   (1 paisa)
    1609935.70::real -> 1609935.8   (10 paise)

Both of those are real invoice totals. This is a blocker for SAP: the payload's
Invoice_Amount is rebuilt from the header components while the ITEM amounts
come from the lines, so a storage snap on either side makes the document fail
SAP's own balance check. It also defeats reconcile_invoice_gst, which goes to
the trouble of rounding GST once on the aggregate only for the result to be
re-rounded by the column.

ROUND() in the USING clause strips the float representation noise from existing
values on the way in. Already-saved rows keep whatever value was stored (a
historical row snapped to .50 stays .50); only the storage type is fixed, so
all future writes are exact.

Revision ID: jnpa71_finance_real_to_numeric
Revises: jnpa70_bill_header_tds_tcs
Create Date: 2026-09-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa71_finance_real_to_numeric'
down_revision: Union[str, None] = 'jnpa70_bill_header_tds_tcs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (numeric_type, scale)
AMOUNT = ('numeric(18,2)', 2)   # money values
RATE = ('numeric(18,4)', 4)     # unit rate / exchange rate
PCT = ('numeric(7,4)', 4)       # gst percentage rates
QTY = ('numeric(18,3)', 3)      # quantities
MISC = ('numeric(12,2)', 2)     # no_of_days / no_of_hrs

COLUMNS = [
    ('bill_header', 'exchange_rate', RATE),
    ('bill_header', 'subtotal', AMOUNT),
    ('bill_header', 'cgst_amount', AMOUNT),
    ('bill_header', 'sgst_amount', AMOUNT),
    ('bill_header', 'igst_amount', AMOUNT),
    ('bill_header', 'tds_amount', AMOUNT),
    ('bill_header', 'tcs_amount', AMOUNT),
    ('bill_header', 'total_amount', AMOUNT),

    ('bill_lines', 'quantity', QTY),
    ('bill_lines', 'rate', RATE),
    ('bill_lines', 'line_amount', AMOUNT),
    ('bill_lines', 'cgst_rate', PCT),
    ('bill_lines', 'sgst_rate', PCT),
    ('bill_lines', 'igst_rate', PCT),
    ('bill_lines', 'cgst_amount', AMOUNT),
    ('bill_lines', 'sgst_amount', AMOUNT),
    ('bill_lines', 'igst_amount', AMOUNT),
    ('bill_lines', 'line_total', AMOUNT),

    ('customer_agreement_lines', 'rate', RATE),
    ('customer_agreement_lines', 'min_charge', AMOUNT),
    ('customer_agreement_lines', 'max_charge', AMOUNT),

    ('invoice_bill_mapping', 'bill_amount', AMOUNT),

    ('invoice_header', 'exchange_rate', RATE),
    ('invoice_header', 'subtotal', AMOUNT),
    ('invoice_header', 'cgst_amount', AMOUNT),
    ('invoice_header', 'sgst_amount', AMOUNT),
    ('invoice_header', 'igst_amount', AMOUNT),
    ('invoice_header', 'tds_amount', AMOUNT),
    ('invoice_header', 'round_off', AMOUNT),
    ('invoice_header', 'total_amount', AMOUNT),
    ('invoice_header', 'no_of_days', MISC),
    ('invoice_header', 'no_of_hrs', MISC),
    ('invoice_header', 'cargo_quantity', QTY),

    ('invoice_lines', 'quantity', QTY),
    ('invoice_lines', 'rate', RATE),
    ('invoice_lines', 'line_amount', AMOUNT),
    ('invoice_lines', 'cgst_rate', PCT),
    ('invoice_lines', 'sgst_rate', PCT),
    ('invoice_lines', 'igst_rate', PCT),
    ('invoice_lines', 'cgst_amount', AMOUNT),
    ('invoice_lines', 'sgst_amount', AMOUNT),
    ('invoice_lines', 'igst_amount', AMOUNT),
    ('invoice_lines', 'line_total', AMOUNT),

    ('service_records', 'billable_quantity', QTY),
]


def _alter(table, column, numtype, scale, using_type):
    """Only touch the column when it is still `real`, so a re-run is a no-op
    and a database where some columns were already converted still upgrades."""
    op.execute(f'''
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = '{table}' AND column_name = '{column}'
                         AND data_type = '{using_type}') THEN
                ALTER TABLE {table} ALTER COLUMN {column} TYPE {numtype}
                    USING ROUND({column}::numeric, {scale});
            END IF;
        END $$;
    ''')


def upgrade() -> None:
    for table, column, (numtype, scale) in COLUMNS:
        _alter(table, column, numtype, scale, 'real')


def downgrade() -> None:
    for table, column, _ in COLUMNS:
        op.execute(f'''
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = '{table}' AND column_name = '{column}'
                             AND data_type = 'numeric') THEN
                    ALTER TABLE {table} ALTER COLUMN {column} TYPE real
                        USING {column}::real;
                END IF;
            END $$;
        ''')

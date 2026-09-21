"""jnpa phase1 - bill_header carries the TDS/TCS its lines computed

save_bill_line has always computed TDS (on the basic) and TCS (on basic + GST)
onto bill_lines, but bill_header had nowhere to put them and its total_amount
was summed as subtotal + GST only. TCS is collected *from* the customer, so
dropping it understated every bill and invoice by the TCS — while SAP's
Invoice_Amount and the IRP's TotInvVal both include it, so the printed
document disagreed with what was posted.

Adds the two columns and rebuilds every bill header from its own lines, which
is idempotent: totals are recomputed in full rather than incremented.

TDS is stored but never subtracted — it is the customer's own withholding at
payment time, not a reduction of the bill.

Revision ID: jnpa70_bill_header_tds_tcs
Revises: jnpa69_vcn_berth_delays
Create Date: 2026-09-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'jnpa70_bill_header_tds_tcs'
down_revision: Union[str, None] = 'jnpa69_vcn_berth_delays'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('''
        ALTER TABLE bill_header ADD COLUMN IF NOT EXISTS tds_amount REAL DEFAULT 0;
        ALTER TABLE bill_header ADD COLUMN IF NOT EXISTS tcs_amount REAL DEFAULT 0;
    ''')
    # Rebuild every header from its lines — same arithmetic as
    # FIN01.model.bill_totals(), so a bill re-saved later lands on the same
    # figures. Bills with no lines keep their stored totals.
    op.execute('''
        UPDATE bill_header h SET
            subtotal     = t.subtotal,
            cgst_amount  = t.cgst_amount,
            sgst_amount  = t.sgst_amount,
            igst_amount  = t.igst_amount,
            tds_amount   = t.tds_amount,
            tcs_amount   = t.tcs_amount,
            total_amount = t.subtotal + t.cgst_amount + t.sgst_amount
                           + t.igst_amount + t.tcs_amount
        FROM (
            SELECT bill_id,
                   ROUND(COALESCE(SUM(line_amount),  0)::numeric, 2) AS subtotal,
                   ROUND(COALESCE(SUM(cgst_amount),  0)::numeric, 2) AS cgst_amount,
                   ROUND(COALESCE(SUM(sgst_amount),  0)::numeric, 2) AS sgst_amount,
                   ROUND(COALESCE(SUM(igst_amount),  0)::numeric, 2) AS igst_amount,
                   ROUND(COALESCE(SUM(tds_amount),   0)::numeric, 2) AS tds_amount,
                   ROUND(COALESCE(SUM(tcs_amount),   0)::numeric, 2) AS tcs_amount
            FROM bill_lines GROUP BY bill_id
        ) t
        WHERE t.bill_id = h.id;
    ''')


def downgrade() -> None:
    op.execute('''
        UPDATE bill_header SET total_amount = total_amount - COALESCE(tcs_amount, 0);
        ALTER TABLE bill_header DROP COLUMN IF EXISTS tds_amount;
        ALTER TABLE bill_header DROP COLUMN IF EXISTS tcs_amount;
    ''')
